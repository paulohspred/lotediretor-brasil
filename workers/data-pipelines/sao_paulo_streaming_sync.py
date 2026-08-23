from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

from connectors import _quality, s3_client
from municipality_lab import _db_deps, load_profile
from sao_paulo_ingestion_preflight import fetch_hits

DB = os.getenv("PLATFORM_DATABASE_URL", "")
S3_BUCKET = os.getenv("S3_BUCKET", "lotediretor")
SOURCE_CODE = "SP_GEOSAMPA_WFS"
PARSER_VERSION = "municipality-wfs-stream-v20"
SCHEMA_VERSION = "wfs-page-manifest-v20"


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/geo+json, application/json;q=0.9, */*;q=0.1",
        "User-Agent": "LoteDiretorBrasil/20 sao-paulo-streaming-sync",
    }


def _bounded_int(value: str | int | None, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _dataset(profile: dict[str, Any], dataset_code: str) -> tuple[dict[str, Any], dict[str, Any]]:
    source = next((item for item in profile.get("sources", []) if item.get("code") == SOURCE_CODE), None)
    if not source or source.get("channel") != "WFS":
        raise RuntimeError("São Paulo profile has no reviewed GeoSampa WFS source")
    dataset = next((item for item in source.get("datasets", []) if item.get("code") == dataset_code), None)
    if not dataset:
        raise RuntimeError(f"unknown São Paulo dataset: {dataset_code}")
    if not dataset.get("typename") or not dataset.get("target_layer_code") or not dataset.get("domain"):
        raise RuntimeError(f"{dataset_code}: typename, target_layer_code and domain are required")
    if not source.get("license_url"):
        raise RuntimeError("GeoSampa license URL is required before ingestion")
    mapping = dataset.get("canonical_mapping") or {}
    if not mapping.get("official_identifier_field"):
        raise RuntimeError(f"{dataset_code}: official_identifier_field must be reviewed before full ingestion")
    return source, dataset


def _canonical_fields(dataset: dict[str, Any]) -> set[str]:
    return {
        str(value)
        for key, value in (dataset.get("canonical_mapping") or {}).items()
        if key.endswith("_field") and value
    }


def _page_size(dataset_code: str) -> int:
    return _bounded_int(os.getenv(f"SP_GEOSAMPA_{dataset_code}_STREAM_PAGE_SIZE"), 2000, 100, 10000)


def _max_pages(dataset_code: str, expected_records: int, page_size: int) -> int:
    # The previous in-memory path capped at 500 pages. Streaming has no one-million-row
    # ceiling, but retains an explicit circuit breaker to avoid an endless/hostile feed.
    needed = max(1, math.ceil(expected_records / page_size) + 2)
    configured = _bounded_int(
        os.getenv(f"SP_GEOSAMPA_{dataset_code}_STREAM_MAX_PAGES"),
        max(needed, 5000),
        needed,
        100000,
    )
    return configured


def _request_page(
    session: requests.Session,
    *,
    url: str,
    typename: str,
    srs_name: str,
    sort_field: str,
    start_index: int,
    count: int,
    attempts: int = 4,
) -> tuple[dict[str, Any], str, int]:
    params = {
        "service": "WFS",
        "request": "GetFeature",
        "version": "2.0.0",
        "outputFormat": "application/json",
        "typeNames": typename,
        "count": count,
        "startIndex": start_index,
        "srsName": srs_name,
        "sortBy": sort_field,
    }
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(url, params=params, headers=_headers(), timeout=180)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
                raise RuntimeError("WFS page is not a GeoJSON FeatureCollection")
            features = payload.get("features")
            if not isinstance(features, list):
                raise RuntimeError("WFS page has no feature list")
            return payload, response.url, response.status_code
        except Exception as exc:  # network/server errors must not silently publish a partial set
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(min(2 ** (attempt - 1), 8))
    raise RuntimeError(f"WFS page fetch failed after {attempts} attempts: {last_error}") from last_error


def _feature_marker(feature: dict[str, Any], official_field: str) -> str | None:
    marker = feature.get("id")
    if marker is not None:
        return f"wfs:{marker}"
    props = feature.get("properties") or {}
    marker = props.get(official_field)
    return f"official:{marker}" if marker not in (None, "") else None


def stage_dataset(
    profile: dict[str, Any],
    dataset_code: str,
    *,
    session: requests.Session | None = None,
    object_store: Any | None = None,
) -> dict[str, Any]:
    """Fetch a complete WFS dataset page-by-page and persist immutable page objects.

    Only one WFS page is held in memory. Publication is impossible from this function:
    it merely returns a complete, content-addressed manifest after proving that the
    source count remained stable, all pages were received, reviewed canonical fields
    remained present and no repeated WFS/official identifier was observed.
    """
    source, dataset = _dataset(profile, dataset_code)
    s = session or requests.Session()
    store = object_store or s3_client()
    expected, hits_before = fetch_hits(s, source["base_url"], dataset["typename"])
    page_size = _page_size(dataset_code)
    max_pages = _max_pages(dataset_code, expected, page_size)
    sort_field = str(dataset["canonical_mapping"]["official_identifier_field"])
    srs_name = str(dataset.get("requested_crs") or "EPSG:4326")
    required_fields = _canonical_fields(dataset)
    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    prefix = f"municipality/{profile['municipality_ibge']}/{dataset_code}/{date_prefix}/pages"

    pages: list[dict[str, Any]] = []
    received = 0
    page_number = 0
    aggregate_checks: dict[str, bool] = {
        "geojson_feature_collection": True,
        "feature_count": True,
        "geometry_presence": True,
        "epsg4326_coordinate_range": True,
        "canonical_schema": True,
        "identifier_uniqueness": True,
    }

    with tempfile.TemporaryDirectory(prefix=f"ld-sp-{dataset_code.lower()}-") as td:
        tracker = sqlite3.connect(str(Path(td) / "identifiers.sqlite"))
        tracker.execute("create table seen(marker text primary key)")

        while received < expected:
            if page_number >= max_pages:
                raise RuntimeError(
                    f"{dataset_code}: streaming circuit breaker reached {max_pages} pages; refuse partial publication"
                )
            payload, url, http_status = _request_page(
                s,
                url=source["base_url"],
                typename=str(dataset["typename"]),
                srs_name=srs_name,
                sort_field=sort_field,
                start_index=received,
                count=min(page_size, expected - received),
            )
            features = payload["features"]
            if not features:
                raise RuntimeError(
                    f"{dataset_code}: WFS returned an empty page at startIndex={received} before expected count {expected}"
                )
            if received + len(features) > expected:
                raise RuntimeError(f"{dataset_code}: WFS returned more rows than numberMatched")

            checks = _quality(payload)
            for check in checks:
                code = str(check.get("code"))
                if code in aggregate_checks and check.get("status") != "PASS":
                    aggregate_checks[code] = False
            observed = {
                str(key)
                for feature in features
                if isinstance(feature, dict)
                for key in (feature.get("properties") or {}).keys()
            }
            if not required_fields.issubset(observed):
                aggregate_checks["canonical_schema"] = False
                missing = sorted(required_fields - observed)
                raise RuntimeError(f"{dataset_code}: canonical schema drift; missing fields {missing}")

            for feature in features:
                if not isinstance(feature, dict):
                    raise RuntimeError(f"{dataset_code}: non-object feature returned")
                marker = _feature_marker(feature, sort_field)
                if marker is None:
                    continue
                try:
                    tracker.execute("insert into seen(marker) values(?)", (marker,))
                except sqlite3.IntegrityError as exc:
                    aggregate_checks["identifier_uniqueness"] = False
                    raise RuntimeError(f"{dataset_code}: repeated feature identifier across pages: {marker}") from exc
            tracker.commit()

            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            page_sha = hashlib.sha256(raw).hexdigest()
            object_key = f"{prefix}/{page_number:06d}-{page_sha}.geojson"
            store.put_object(
                Bucket=S3_BUCKET,
                Key=object_key,
                Body=raw,
                ContentType="application/geo+json",
                Metadata={
                    "sha256": page_sha,
                    "source": SOURCE_CODE,
                    "dataset": dataset_code,
                    "start-index": str(received),
                },
            )
            pages.append(
                {
                    "page": page_number,
                    "start_index": received,
                    "records": len(features),
                    "sha256": page_sha,
                    "object_key": object_key,
                    "http_status": http_status,
                    "url": url,
                }
            )
            received += len(features)
            page_number += 1
        tracker.close()

    expected_after, hits_after = fetch_hits(s, source["base_url"], dataset["typename"])
    if expected_after != expected:
        raise RuntimeError(
            f"{dataset_code}: source changed during sync ({expected} -> {expected_after}); refuse mixed snapshot"
        )
    if received != expected:
        raise RuntimeError(f"{dataset_code}: incomplete pagination {received}/{expected}; refuse publication")
    blocking_checks = [name for name, passed in aggregate_checks.items() if not passed]
    if blocking_checks:
        raise RuntimeError(f"{dataset_code}: aggregate quality failed: {blocking_checks}")

    immutable = {
        "schema_version": SCHEMA_VERSION,
        "source_code": SOURCE_CODE,
        "municipality_ibge": profile["municipality_ibge"],
        "dataset_code": dataset_code,
        "typename": dataset["typename"],
        "requested_crs": srs_name,
        "sort_field": sort_field,
        "expected_records": expected,
        "received_records": received,
        "page_size": page_size,
        "pages": pages,
        "quality": aggregate_checks,
        "license_url": source["license_url"],
        "source_revision": dataset.get("source_revision"),
        "canonical_mapping": dataset.get("canonical_mapping") or {},
    }
    canonical = json.dumps(immutable, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    manifest_sha = hashlib.sha256(canonical).hexdigest()
    manifest = {
        **immutable,
        "manifest_sha256": manifest_sha,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "hits_before": hits_before,
        "hits_after": hits_after,
        "publication_performed": False,
    }
    manifest_key = (
        f"municipality/{profile['municipality_ibge']}/{dataset_code}/{date_prefix}/manifest-{manifest_sha}.json"
    )
    store.put_object(
        Bucket=S3_BUCKET,
        Key=manifest_key,
        Body=json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json",
        Metadata={"sha256": manifest_sha, "source": SOURCE_CODE, "dataset": dataset_code},
    )
    manifest["manifest_object_key"] = manifest_key
    return manifest


def _iter_manifest_features(manifest: dict[str, Any], store: Any) -> Iterable[dict[str, Any]]:
    for page in manifest["pages"]:
        body = store.get_object(Bucket=S3_BUCKET, Key=page["object_key"])["Body"].read()
        if hashlib.sha256(body).hexdigest() != page["sha256"]:
            raise RuntimeError(f"page object checksum mismatch: {page['object_key']}")
        payload = json.loads(body)
        features = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(features, list) or len(features) != page["records"]:
            raise RuntimeError(f"page object record mismatch: {page['object_key']}")
        yield from features


def publish_staged_dataset(profile: dict[str, Any], manifest: dict[str, Any], *, object_store: Any | None = None) -> dict[str, Any]:
    """Atomically load a complete staged manifest and activate publication.

    All geo.feature rows and the source publication switch occur in one PostgreSQL
    transaction. A page checksum, geometry conversion, record count or DB failure rolls
    the transaction back, leaving the previous active snapshot untouched.
    """
    if manifest.get("publication_performed") is not False:
        raise RuntimeError("only an un-published staging manifest is accepted")
    if manifest.get("received_records") != manifest.get("expected_records"):
        raise RuntimeError("incomplete manifest cannot be published")
    dataset_code = str(manifest["dataset_code"])
    source, dataset = _dataset(profile, dataset_code)
    if manifest.get("municipality_ibge") != profile["municipality_ibge"]:
        raise RuntimeError("manifest municipality mismatch")
    if manifest.get("typename") != dataset.get("typename"):
        raise RuntimeError("manifest typename no longer matches reviewed profile")
    if manifest.get("canonical_mapping") != (dataset.get("canonical_mapping") or {}):
        raise RuntimeError("manifest canonical mapping no longer matches reviewed profile")
    if not DB:
        raise RuntimeError("PLATFORM_DATABASE_URL_required_for_streaming_publication")

    psycopg, Jsonb = _db_deps()
    store = object_store or s3_client()
    ibge = profile["municipality_ibge"]
    layer_code = dataset["target_layer_code"]
    domain = str(dataset["domain"]).upper()
    expected = int(manifest["expected_records"])
    sha = str(manifest["manifest_sha256"])

    with psycopg.connect(DB) as c, c.transaction():
        source_id = c.execute(
            """insert into source.registry(code,title,authority,access_class,channel,base_url,data_owner,cadence,health,license_terms,provenance)
            values(%s,%s,%s,'B','WFS',%s,%s,'ON_DEMAND','OK',%s,%s)
            on conflict(code) do update set authority=excluded.authority,channel=excluded.channel,base_url=excluded.base_url,
              license_terms=excluded.license_terms,provenance=source.registry.provenance||excluded.provenance returning id""",
            (
                SOURCE_CODE,
                SOURCE_CODE,
                source["authority"],
                source["base_url"],
                source["authority"],
                source.get("license", "REVIEW_REQUIRED"),
                Jsonb({"official": True, "municipality_ibge": ibge, "license_url": source["license_url"]}),
            ),
        ).fetchone()[0]
        c.execute(
            """insert into source.coverage(source_id,municipality_ibge,dataset_code,scope,availability_status,ingestion_status,access_class,metadata)
            values(%s,%s,%s,'MUNICIPAL','AVAILABLE','STAGED','B',%s)
            on conflict(source_id,municipality_ibge,dataset_code) do update set availability_status='AVAILABLE',
              ingestion_status='STAGED',metadata=excluded.metadata,updated_at=now()""",
            (source_id, ibge, dataset_code, Jsonb({"manifest_sha256": sha, "typename": dataset["typename"]})),
        )
        snapshot_id = c.execute(
            """insert into source.snapshot(source_id,source_date,parser_version,sha256,object_key,metadata,status,quality,record_count,validation_status,schema_version)
            values(%s,now(),%s,%s,%s,%s,'VALIDATED',%s,%s,'PASS',%s)
            on conflict(source_id,sha256) do update set object_key=excluded.object_key,metadata=excluded.metadata,status='VALIDATED',
              quality=excluded.quality,record_count=excluded.record_count,validation_status='PASS',schema_version=excluded.schema_version returning id""",
            (
                source_id,
                PARSER_VERSION,
                sha,
                manifest["manifest_object_key"],
                Jsonb({"manifest": {k: v for k, v in manifest.items() if k != "pages"}, "pages": manifest["pages"]}),
                Jsonb({"checks": manifest["quality"]}),
                expected,
                SCHEMA_VERSION,
            ),
        ).fetchone()[0]
        active = c.execute(
            """select snapshot_id from source.publication where source_id=%s and municipality_ibge=%s
               and dataset_code=%s and status='ACTIVE' for update""",
            (source_id, ibge, dataset_code),
        ).fetchone()
        if active and active[0] == snapshot_id:
            return {
                "status": "ALREADY_PUBLISHED",
                "municipality_ibge": ibge,
                "dataset": dataset_code,
                "snapshotId": str(snapshot_id),
                "records": expected,
            }
        layer_id = c.execute(
            """insert into geo.layer(code,title,domain,municipality_ibge,source_id,dataset_code,geometry_type,visibility,status,metadata)
            values(%s,%s,%s,%s,%s,%s,'GEOMETRY','PUBLIC','ACTIVE',%s)
            on conflict(code) do update set source_id=excluded.source_id,dataset_code=excluded.dataset_code,status='ACTIVE',
              metadata=excluded.metadata,updated_at=now() returning id""",
            (
                layer_code,
                layer_code,
                domain,
                ibge,
                source_id,
                dataset_code,
                Jsonb({"typename": dataset["typename"], "license_url": source["license_url"], "srs_name": dataset.get("requested_crs")}),
            ),
        ).fetchone()[0]
        c.execute("delete from geo.feature where layer_id=%s and source_snapshot_id=%s", (layer_id, snapshot_id))

        loaded = 0
        batch: list[tuple[Any, ...]] = []
        official_field = str(dataset["canonical_mapping"]["official_identifier_field"])
        for feature in _iter_manifest_features(manifest, store):
            geometry = feature.get("geometry")
            props = feature.get("properties") or {}
            if not isinstance(geometry, dict) or not geometry.get("type"):
                raise RuntimeError(f"{dataset_code}: feature without geometry during publication")
            official = props.get(official_field)
            if official in (None, ""):
                official = feature.get("id")
            batch.append((layer_id, snapshot_id, str(official) if official not in (None, "") else None, json.dumps(geometry), Jsonb(props)))
            if len(batch) >= 2000:
                c.executemany(
                    """insert into geo.feature(layer_id,tenant_id,source_snapshot_id,official_identifier,geom,attributes)
                    values(%s,null,%s,%s,st_setsrid(st_geomfromgeojson(%s),4326),%s)""",
                    batch,
                )
                loaded += len(batch)
                batch.clear()
        if batch:
            c.executemany(
                """insert into geo.feature(layer_id,tenant_id,source_snapshot_id,official_identifier,geom,attributes)
                values(%s,null,%s,%s,st_setsrid(st_geomfromgeojson(%s),4326),%s)""",
                batch,
            )
            loaded += len(batch)
        if loaded != expected:
            raise RuntimeError(f"{dataset_code}: database load incomplete {loaded}/{expected}; transaction will roll back")

        quality_rows = {
            "complete_pagination": ("PASS", {"expected": expected}, {"loaded": loaded}),
            "canonical_schema": ("PASS", {"required": sorted(_canonical_fields(dataset))}, {"mapping": dataset["canonical_mapping"]}),
            "geometry_presence": ("PASS", {"with_geometry": expected}, {"with_geometry": loaded}),
            "identifier_uniqueness": ("PASS", {"duplicates": 0}, {"duplicates": 0}),
        }
        for check_code, (status, expected_value, observed_value) in quality_rows.items():
            c.execute(
                """insert into data_quality.result(source_id,snapshot_id,check_code,severity,status,expected,observed)
                values(%s,%s,%s,'ERROR',%s,%s,%s)
                on conflict(snapshot_id,check_code) do update set status=excluded.status,expected=excluded.expected,
                  observed=excluded.observed,checked_at=now()""",
                (source_id, snapshot_id, check_code, status, Jsonb(expected_value), Jsonb(observed_value)),
            )

        previous = active[0] if active else None
        c.execute(
            """update source.publication set status='INACTIVE',deactivated_at=now()
               where source_id=%s and municipality_ibge=%s and dataset_code=%s and status='ACTIVE'""",
            (source_id, ibge, dataset_code),
        )
        c.execute(
            """insert into source.publication(source_id,municipality_ibge,dataset_code,snapshot_id,status)
               values(%s,%s,%s,%s,'ACTIVE')""",
            (source_id, ibge, dataset_code, snapshot_id),
        )
        c.execute("update source.snapshot set status='PUBLISHED',published_at=coalesce(published_at,now()) where id=%s", (snapshot_id,))
        c.execute(
            """update source.coverage set availability_status='AVAILABLE',ingestion_status='PUBLISHED',parser_version=%s,
               last_checked_at=now(),last_source_update=now(),evidence_hash=%s,metadata=metadata||%s
               where source_id=%s and municipality_ibge=%s and dataset_code=%s""",
            (
                PARSER_VERSION,
                sha,
                Jsonb({"manifest_object_key": manifest["manifest_object_key"], "manifest_sha256": sha, "layer_code": layer_code}),
                source_id,
                ibge,
                dataset_code,
            ),
        )
        c.execute(
            """insert into source.publication_event(source_id,municipality_ibge,dataset_code,previous_snapshot_id,next_snapshot_id,action,actor,reason)
               values(%s,%s,%s,%s,%s,'ACTIVATE','municipality-stream-v20','complete WFS streaming snapshot passed quality and count gates')""",
            (source_id, ibge, dataset_code, previous, snapshot_id),
        )
    return {
        "status": "PUBLISHED",
        "municipality_ibge": ibge,
        "dataset": dataset_code,
        "snapshotId": str(snapshot_id),
        "layerId": str(layer_id),
        "manifestSha256": sha,
        "received": expected,
        "loaded": loaded,
    }


def sync_dataset(profile: dict[str, Any], dataset_code: str) -> dict[str, Any]:
    manifest = stage_dataset(profile, dataset_code)
    return publish_staged_dataset(profile, manifest)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    profile_path = Path(os.getenv("SP_PROFILE", root / "data/municipality-labs/sao-paulo-3550308.json"))
    dataset_code = os.getenv("SP_DATASET", "PARCEL").strip().upper()
    result = sync_dataset(load_profile(str(profile_path)), dataset_code)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
