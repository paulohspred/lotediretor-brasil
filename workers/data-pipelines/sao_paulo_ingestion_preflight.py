from __future__ import annotations

import json
import math
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from municipality_lab import load_profile


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/json, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1",
        "User-Agent": "LoteDiretorBrasil/19.0.0-rc.3 sao-paulo-ingestion-preflight",
    }


def _bounded_int(value: str | int | None, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def capacity_for(dataset_code: str) -> tuple[int, int]:
    prefix = f"SP_GEOSAMPA_{dataset_code}"
    page_size = _bounded_int(os.getenv(f"{prefix}_SOURCE_PAGE_SIZE"), 2000, 1, 10000)
    max_pages = _bounded_int(os.getenv(f"{prefix}_SOURCE_MAX_PAGES"), 500, 1, 5000)
    return page_size, max_pages


def parse_number_matched(response: requests.Response) -> int:
    content_type = (response.headers.get("content-type") or "").lower()
    text = response.text.strip()
    if "json" in content_type or text.startswith("{"):
        payload = response.json()
        value = payload.get("numberMatched") if isinstance(payload, dict) else None
    else:
        root = ET.fromstring(response.content)
        value = root.attrib.get("numberMatched")
    if value in (None, "unknown"):
        raise RuntimeError("WFS hits response did not provide a finite numberMatched")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"invalid WFS numberMatched: {value!r}") from exc
    if result < 0:
        raise RuntimeError(f"negative WFS numberMatched: {result}")
    return result


def fetch_hits(session: requests.Session, base_url: str, typename: str) -> tuple[int, dict[str, Any]]:
    params = {
        "service": "WFS",
        "request": "GetFeature",
        "version": "2.0.0",
        "typeNames": typename,
        "resultType": "hits",
    }
    response = session.get(base_url, params=params, headers=_headers(), timeout=180)
    response.raise_for_status()
    return parse_number_matched(response), {
        "http_status": response.status_code,
        "url": response.url,
        "mode": "WFS_HITS_ONLY",
    }


def fetch_sample(session: requests.Session, base_url: str, typename: str, srs_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    params = {
        "service": "WFS",
        "request": "GetFeature",
        "version": "2.0.0",
        "outputFormat": "application/json",
        "typeNames": typename,
        "count": 1,
        "startIndex": 0,
        "srsName": srs_name,
    }
    response = session.get(base_url, params=params, headers=_headers(), timeout=180)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise RuntimeError(f"{typename}: sample is not a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise RuntimeError(f"{typename}: sample returned no feature")
    feature = features[0]
    geometry = feature.get("geometry") if isinstance(feature, dict) else None
    if not isinstance(geometry, dict) or not geometry.get("type"):
        raise RuntimeError(f"{typename}: sample returned no geometry")
    properties = feature.get("properties") if isinstance(feature, dict) else None
    if not isinstance(properties, dict):
        raise RuntimeError(f"{typename}: sample returned no properties")
    return {
        "feature_id": feature.get("id"),
        "geometry_type": geometry.get("type"),
        "property_keys": sorted(str(key) for key in properties),
    }, {
        "http_status": response.status_code,
        "url": response.url,
        "mode": "WFS_SAMPLE_ONLY",
    }


def canonical_fields(dataset: dict[str, Any]) -> list[str]:
    mapping = dataset.get("canonical_mapping") or {}
    return sorted({str(value) for key, value in mapping.items() if key.endswith("_field") and value})


def evaluate_dataset(dataset: dict[str, Any], source: dict[str, Any], session: requests.Session) -> dict[str, Any]:
    code = str(dataset["code"])
    typename = str(dataset.get("typename") or "").strip()
    if not typename:
        raise RuntimeError(f"{code}: typename is required")
    srs_name = str(dataset.get("requested_crs") or "EPSG:4326")
    count, hits_meta = fetch_hits(session, source["base_url"], typename)
    sample, sample_meta = fetch_sample(session, source["base_url"], typename, srs_name)
    required_fields = canonical_fields(dataset)
    observed_fields = set(sample["property_keys"])
    missing_fields = sorted(field for field in required_fields if field not in observed_fields)
    page_size, max_pages = capacity_for(code)
    estimated_pages = math.ceil(count / page_size) if count else 0
    capacity_records = page_size * max_pages
    capacity_ok = estimated_pages <= max_pages
    schema_ok = not missing_fields
    status = (
        "READY_FOR_FULL_SYNC"
        if schema_ok and capacity_ok
        else "FULL_SYNC_REQUIRES_CAPACITY_PLAN"
        if schema_ok
        else "BLOCKED_SCHEMA_DRIFT"
    )
    return {
        "dataset_code": code,
        "typename": typename,
        "status": status,
        "number_matched": count,
        "requested_crs": srs_name,
        "page_size": page_size,
        "max_pages": max_pages,
        "capacity_records": capacity_records,
        "estimated_pages": estimated_pages,
        "capacity_ok": capacity_ok,
        "schema_ok": schema_ok,
        "required_canonical_fields": required_fields,
        "missing_canonical_fields": missing_fields,
        "sample": sample,
        "hits_fetch": hits_meta,
        "sample_fetch": sample_meta,
    }


def run(profile: dict[str, Any], session: requests.Session | None = None) -> dict[str, Any]:
    s = session or requests.Session()
    source = next(item for item in profile["sources"] if item["code"] == "SP_GEOSAMPA_WFS")
    datasets = {item["code"]: item for item in source["datasets"]}
    results = [evaluate_dataset(datasets[code], source, s) for code in ("PARCEL", "ZONEAMENTO")]
    blocking = [item for item in results if item["status"] == "BLOCKED_SCHEMA_DRIFT"]
    capacity = [item for item in results if item["status"] == "FULL_SYNC_REQUIRES_CAPACITY_PLAN"]
    overall = "BLOCKED_SCHEMA_DRIFT" if blocking else "CAPACITY_PLAN_REQUIRED" if capacity else "READY_FOR_FULL_SYNC"
    return {
        "status": overall,
        "municipality_ibge": profile["municipality_ibge"],
        "municipality": profile["name"],
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "datasets": results,
        "publication_performed": False,
        "note": "Preflight only. No snapshot, database write, canonical promotion or publication is performed here.",
    }


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    profile_path = Path(os.getenv("SP_PROFILE", root / "data/municipality-labs/sao-paulo-3550308.json"))
    output_path = Path(os.getenv("SP_PREFLIGHT_OUTPUT", root / "artifacts/sao-paulo-ingestion-preflight/summary.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = run(load_profile(str(profile_path)))
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "BLOCKED_SCHEMA_DRIFT":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
