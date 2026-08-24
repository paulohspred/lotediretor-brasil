from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from sao_paulo_golden_candidates import PROFILE, _dataset, build_candidate


def select_batch(profile: dict[str, Any], count: int, base_date: str, timeout: int = 20) -> dict[str, Any]:
    source, dataset = _dataset(profile, "PARCEL")
    if source.get("code") != "SP_GEOSAMPA_WFS" or source.get("channel") != "WFS":
        raise RuntimeError("unexpected_parcel_source_contract")
    if not source.get("license_url") or not dataset.get("typename"):
        raise RuntimeError("parcel_source_not_reviewed_for_access")

    mapping = dataset.get("canonical_mapping") or {}
    sort_field = mapping.get("official_identifier_field")
    if not sort_field:
        raise RuntimeError("official_identifier_field_required")

    response = requests.get(
        source["base_url"],
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": dataset["typename"],
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",
            "count": count,
            "startIndex": 0,
            "sortBy": f"{sort_field} A",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    features = payload.get("features") or []
    if len(features) < count:
        raise RuntimeError(f"wfs_batch_returned_too_few_features:{len(features)}:{count}")

    payload_sha256 = hashlib.sha256(response.content).hexdigest()
    candidates: list[dict[str, Any]] = []
    ids: set[str] = set()
    for offset, feature in enumerate(features[:count]):
        candidate = build_candidate(feature, dataset, source, offset, payload_sha256, base_date)
        oid = candidate["expected_official_reference"]
        if oid in ids:
            raise RuntimeError(f"duplicate_official_identifier:{oid}")
        ids.add(oid)
        candidates.append(candidate)

    number_matched = payload.get("numberMatched", payload.get("totalFeatures"))
    try:
        number_matched = int(number_matched) if number_matched is not None else None
    except (TypeError, ValueError):
        number_matched = None

    profile_bytes = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
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
            "live_number_matched": number_matched,
            "wfs_response_sha256": payload_sha256,
        },
        "selection": {
            "strategy": "stable_sorted_prefix_single_wfs_page",
            "requested": count,
            "selected": len(candidates),
            "offsets": list(range(len(candidates))),
            "representative_sampling_claimed": False,
        },
        "candidates": candidates,
        "non_claims": [
            "Candidate selection is not municipal homologation.",
            "This bounded stable prefix is an operational candidate set, not a statistical or geographic representativeness claim.",
            "Observed WFS attributes are not a substitute for a published canonical snapshot.",
            "No zone or urban parameter is inferred by this selector.",
            "Every PASS still requires human review and evidence required by the validation plan.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Select a bounded stable São Paulo parcel candidate page from official GeoSampa WFS")
    parser.add_argument("--profile", default=str(PROFILE))
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--base-date", required=True)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--output", default="artifacts/sao-paulo-golden-candidates/candidates.json")
    args = parser.parse_args()
    if not 10 <= args.count <= 20:
        raise SystemExit("--count must be between 10 and 20 for the São Paulo golden-lot plan")

    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    result = select_batch(profile, args.count, args.base_date, args.timeout)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "selected": len(result["candidates"]), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
