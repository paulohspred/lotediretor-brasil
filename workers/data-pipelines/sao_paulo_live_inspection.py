from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from municipality_lab import load_profile


def inspect_wfs_sample(source: dict[str, Any], typename: str, srs_name: str = "EPSG:4326", count: int = 5) -> dict[str, Any]:
    """Read a bounded WFS sample for connectivity/schema evidence only.

    This deliberately does not call the production publication fetcher. The production
    path must continue to reject partial pagination; this inspection path is explicitly
    non-publishing and marks its evidence as a partial sample.
    """
    if source.get("channel") != "WFS":
        raise RuntimeError("profile source is not WFS")
    if not typename:
        raise RuntimeError("typename is required")

    params = {
        "service": "WFS",
        "request": "GetFeature",
        "version": "2.0.0",
        "outputFormat": "application/json",
        "typeNames": typename,
        "count": max(1, min(int(count), 20)),
        "startIndex": 0,
        "srsName": srs_name,
    }
    headers = {
        "Accept": "application/geo+json, application/json;q=0.9, */*;q=0.1",
        "User-Agent": "LoteDiretorBrasil/19.0.0-rc.3 source-inspection",
    }
    response = requests.get(source["base_url"], params=params, headers=headers, timeout=180)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise RuntimeError(f"{typename}: WFS sample did not return a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise RuntimeError(f"{typename}: WFS sample returned no features")

    property_keys = sorted({str(key) for feature in features for key in (feature.get("properties") or {}).keys()})
    sample = [
        {
            "id": feature.get("id"),
            "geometry_type": (feature.get("geometry") or {}).get("type"),
            "properties": feature.get("properties") or {},
        }
        for feature in features[:3]
    ]
    return {
        "status": "INSPECTED",
        "typename": typename,
        "srs_name": srs_name,
        "property_keys": property_keys,
        "sample": sample,
        "fetch": {
            "http_status": response.status_code,
            "mode": "WFS_SAMPLE_ONLY",
            "partial_sample": True,
            "requested_count": params["count"],
            "received_count": len(features),
            "url": response.url,
        },
    }


def main() -> None:
    profile_path = Path(os.getenv("SP_PROFILE", "../../data/municipality-labs/sao-paulo-3550308.json"))
    out_dir = Path(os.getenv("SP_INSPECTION_DIR", "../../artifacts/sao-paulo-live-source"))
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = load_profile(str(profile_path))
    source_code = "SP_GEOSAMPA_WFS"
    source = next(item for item in profile["sources"] if item["code"] == source_code)
    datasets = {item["code"]: item for item in source["datasets"]}

    results: dict[str, dict[str, Any]] = {}
    for key, dataset_code in (("parcel", "PARCEL"), ("zoning", "ZONEAMENTO")):
        dataset = datasets[dataset_code]
        typename = dataset.get("typename")
        if not typename:
            raise RuntimeError(f"{dataset_code}: typename missing from reviewed profile")
        result = inspect_wfs_sample(source, typename, "EPSG:4326", 5)
        if result.get("status") != "INSPECTED":
            raise RuntimeError(f"{dataset_code}: unexpected inspection status")
        if not result.get("property_keys"):
            raise RuntimeError(f"{dataset_code}: WFS returned no property schema")
        sample = result.get("sample") or []
        if not sample or not any(item.get("geometry_type") for item in sample):
            raise RuntimeError(f"{dataset_code}: WFS returned no geometry sample")
        fetch = result.get("fetch") or {}
        if fetch.get("mode") != "WFS_SAMPLE_ONLY" or fetch.get("partial_sample") is not True:
            raise RuntimeError(f"{dataset_code}: inspection evidence is not explicitly sample-only")

        target = out_dir / f"{key}.json"
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        results[key] = {
            "dataset_code": dataset_code,
            "typename": typename,
            "property_keys": result["property_keys"],
            "sample_count": len(sample),
            "fetch": fetch,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
        print(f"{dataset_code}: live WFS sample inspection PASS")

    summary = {
        "status": "LIVE_INSPECTION_PASS",
        "municipality_ibge": profile["municipality_ibge"],
        "municipality": profile["name"],
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "records": results,
        "note": "Connectivity/schema/sample evidence only; production ingestion still requires complete pagination, QA and promotion.",
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
