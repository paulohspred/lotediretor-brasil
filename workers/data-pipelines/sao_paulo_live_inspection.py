from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from municipality_lab import inspect_wfs, load_profile


def main() -> None:
    profile_path = Path(os.getenv("SP_PROFILE", "../../data/municipality-labs/sao-paulo-3550308.json"))
    out_dir = Path(os.getenv("SP_INSPECTION_DIR", "../../artifacts/sao-paulo-live-source"))
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = load_profile(str(profile_path))
    source_code = "SP_GEOSAMPA_WFS"
    source = next(item for item in profile["sources"] if item["code"] == source_code)
    datasets = {item["code"]: item for item in source["datasets"]}

    results: dict[str, dict] = {}
    for key, dataset_code in (("parcel", "PARCEL"), ("zoning", "ZONEAMENTO")):
        dataset = datasets[dataset_code]
        typename = dataset.get("typename")
        if not typename:
            raise RuntimeError(f"{dataset_code}: typename missing from reviewed profile")
        result = inspect_wfs(profile, source_code, typename, "EPSG:4326")
        if result.get("status") != "INSPECTED":
            raise RuntimeError(f"{dataset_code}: unexpected inspection status")
        if not result.get("property_keys"):
            raise RuntimeError(f"{dataset_code}: WFS returned no property schema")
        sample = result.get("sample") or []
        if not sample or not any(item.get("geometry_type") for item in sample):
            raise RuntimeError(f"{dataset_code}: WFS returned no geometry sample")
        if not result.get("fetch"):
            raise RuntimeError(f"{dataset_code}: missing fetch provenance")
        target = out_dir / f"{key}.json"
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        results[key] = {
            "dataset_code": dataset_code,
            "typename": typename,
            "property_keys": result["property_keys"],
            "sample_count": len(sample),
            "fetch": result["fetch"],
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
        print(f"{dataset_code}: live WFS inspection PASS")

    summary = {
        "status": "LIVE_INSPECTION_PASS",
        "municipality_ibge": profile["municipality_ibge"],
        "municipality": profile["name"],
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "records": results,
        "note": "Connectivity/schema/sample evidence only; this is not ingestion or municipal homologation.",
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
