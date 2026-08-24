from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from shapely.geometry import shape

PROFILE = Path("data/municipality-labs/sao-paulo-3550308.json")


def _dataset(profile: dict[str, Any], code: str) -> tuple[dict[str, Any], dict[str, Any]]:
    for source in profile.get("sources", []):
        for dataset in source.get("datasets", []):
            if dataset.get("code") == code:
                return source, dataset
    raise RuntimeError(f"dataset_not_found:{code}")


def _hits(base_url: str, typename: str, timeout: int) -> int:
    response = requests.get(base_url, params={
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": typename,
        "resultType": "hits",
    }, timeout=timeout)
    response.raise_for_status()
    match = re.search(r'numberMatched=["\'](\d+)["\']', response.text)
    if not match:
        raise RuntimeError("wfs_hits_missing_numberMatched")
    return int(match.group(1))


def deterministic_offsets(total: int, count: int) -> list[int]:
    if total <= 0 or count <= 0:
        return []
    count = min(count, total)
    raw = [min(total - 1, math.floor((i + 0.5) * total / count)) for i in range(count)]
    offsets: list[int] = []
    seen = set()
    for value in raw:
        if value not in seen:
            offsets.append(value)
            seen.add(value)
    return offsets


def _one(base_url: str, typename: str, sort_field: str, offset: int, timeout: int) -> tuple[dict[str, Any], str]:
    response = requests.get(base_url, params={
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": typename,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "count": 1,
        "startIndex": offset,
        "sortBy": f"{sort_field} A",
    }, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    features = payload.get("features") or []
    if len(features) != 1:
        raise RuntimeError(f"wfs_expected_one_feature_at_offset:{offset}")
    digest = hashlib.sha256(response.content).hexdigest()
    return features[0], digest


def _point(geometry: dict[str, Any]) -> dict[str, float]:
    geom = shape(geometry)
    if geom.is_empty or not geom.is_valid:
        geom = geom.buffer(0)
    if geom.is_empty:
        raise RuntimeError("parcel_geometry_empty")
    point = geom.representative_point()
    return {"lat": round(float(point.y), 8), "lon": round(float(point.x), 8)}


def build_candidate(feature: dict[str, Any], dataset: dict[str, Any], source: dict[str, Any], offset: int, payload_sha256: str, base_date: str) -> dict[str, Any]:
    props = feature.get("properties") or {}
    mapping = dataset.get("canonical_mapping") or {}
    id_field = mapping.get("official_identifier_field")
    area_field = mapping.get("land_area_m2_field")
    street_field = mapping.get("street_name_field")
    number_field = mapping.get("street_number_field")
    official_id = str(props.get(id_field) or "").strip() if id_field else ""
    if not official_id:
        raise RuntimeError(f"parcel_missing_official_identifier_at_offset:{offset}")
    geometry = feature.get("geometry")
    if not geometry:
        raise RuntimeError(f"parcel_missing_geometry:{official_id}")

    return {
        "case_code": f"3550308-PARCEL-{official_id}",
        "input_kind": "OFFICIAL_PARCEL_ID",
        "input_payload": {
            "official_parcel_id": official_id,
            "point": _point(geometry),
        },
        "base_date": base_date,
        "expected_official_reference": official_id,
        "expected_zone_code": None,
        "expected_parameters": {},
        "human_reviewer": None,
        "human_reviewed_at": None,
        "status": "PENDING_HUMAN_REVIEW",
        "source_observation": {
            "source_code": source.get("code"),
            "authority": source.get("authority"),
            "dataset_code": dataset.get("code"),
            "typename": dataset.get("typename"),
            "wfs_offset": offset,
            "payload_sha256": payload_sha256,
            "parcel_area_m2_observed": props.get(area_field) if area_field else None,
            "street_observed": props.get(street_field) if street_field else None,
            "street_number_observed": props.get(number_field) if number_field else None,
        },
        "notes": "Candidate selected from the reviewed official parcel WFS contract. Zone, legal parameters and PASS require separate human review and published snapshot evidence.",
    }


def select(profile: dict[str, Any], count: int, base_date: str, timeout: int = 30) -> dict[str, Any]:
    source, dataset = _dataset(profile, "PARCEL")
    if source.get("code") != "SP_GEOSAMPA_WFS" or source.get("channel") != "WFS":
        raise RuntimeError("unexpected_parcel_source_contract")
    if not source.get("license_url") or not dataset.get("typename"):
        raise RuntimeError("parcel_source_not_reviewed_for_access")
    mapping = dataset.get("canonical_mapping") or {}
    sort_field = mapping.get("official_identifier_field")
    if not sort_field:
        raise RuntimeError("official_identifier_field_required")

    total = _hits(source["base_url"], dataset["typename"], timeout)
    offsets = deterministic_offsets(total, count)
    candidates = []
    ids = set()
    for offset in offsets:
        feature, digest = _one(source["base_url"], dataset["typename"], sort_field, offset, timeout)
        candidate = build_candidate(feature, dataset, source, offset, digest, base_date)
        oid = candidate["expected_official_reference"]
        if oid in ids:
            raise RuntimeError(f"duplicate_official_identifier:{oid}")
        ids.add(oid)
        candidates.append(candidate)

    profile_bytes = PROFILE.read_bytes() if PROFILE.exists() else json.dumps(profile, sort_keys=True).encode()
    return {
        "municipality_ibge": profile["municipality_ibge"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_date": base_date,
        "status": "CANDIDATES_ONLY_PENDING_HUMAN_REVIEW",
        "source_profile_sha256": hashlib.sha256(profile_bytes).hexdigest(),
        "source": {
            "code": source.get("code"),
            "authority": source.get("authority"),
            "base_url": source.get("base_url"),
            "license": source.get("license"),
            "license_url": source.get("license_url"),
            "dataset": dataset.get("code"),
            "typename": dataset.get("typename"),
            "live_number_matched": total,
        },
        "selection": {
            "strategy": "evenly_spaced_offsets_sorted_by_official_identifier",
            "requested": count,
            "selected": len(candidates),
            "offsets": offsets,
        },
        "candidates": candidates,
        "non_claims": [
            "Candidate selection is not municipal homologation.",
            "Observed WFS attributes are not a substitute for a published canonical snapshot.",
            "No zone or urban parameter is inferred by this selector.",
            "Every PASS still requires human review and evidence required by the validation plan.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Select reproducible São Paulo parcel candidates from official GeoSampa WFS without inventing legal expectations")
    parser.add_argument("--profile", default=str(PROFILE))
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--base-date", required=True)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--output", default="artifacts/sao-paulo-golden-candidates/candidates.json")
    args = parser.parse_args()
    if not 10 <= args.count <= 20:
        raise SystemExit("--count must be between 10 and 20 for the São Paulo golden-lot plan")
    profile_path = Path(args.profile)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    global PROFILE
    PROFILE = profile_path
    result = select(profile, args.count, args.base_date, args.timeout)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "selected": len(result["candidates"]), "numberMatched": result["source"]["live_number_matched"], "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
