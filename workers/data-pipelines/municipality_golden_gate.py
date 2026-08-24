from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.I)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _iso_datetime(value: Any) -> bool:
    text = _text(value)
    if not text:
        return False
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _case_issues(case: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    code = _text(case.get("case_code")) or "<missing-case-code>"

    for field in plan.get("required_case_fields", []):
        value = case.get(field)
        if value is None or value == "" or value == {} or value == []:
            issues.append(f"{code}:missing:{field}")

    if _text(case.get("status")).upper() != "PASS":
        issues.append(f"{code}:status_not_PASS")

    reviewer = case.get("human_reviewer") or case.get("reviewer")
    reviewed_at = case.get("human_reviewed_at") or case.get("reviewed_at")
    if not _text(reviewer):
        issues.append(f"{code}:human_reviewer_required")
    if not _iso_datetime(reviewed_at):
        issues.append(f"{code}:human_reviewed_at_invalid")

    evidence = case.get("evidence") if isinstance(case.get("evidence"), dict) else {}
    for field in plan.get("required_case_evidence", []):
        value = evidence.get(field)
        if field.endswith("sha256"):
            if not _SHA256.fullmatch(_text(value)):
                issues.append(f"{code}:invalid_evidence_hash:{field}")
        elif value is None or value == "" or value == [] or value == {}:
            issues.append(f"{code}:missing_evidence:{field}")

    dimensions = case.get("review_dimensions") if isinstance(case.get("review_dimensions"), dict) else {}
    for dimension in plan.get("required_review_dimensions", []):
        review = dimensions.get(dimension)
        if not isinstance(review, dict):
            issues.append(f"{code}:missing_review_dimension:{dimension}")
            continue
        disposition = _text(review.get("disposition")).upper()
        if disposition not in {"CONFIRMED", "NOT_APPLICABLE", "UNKNOWN"}:
            issues.append(f"{code}:invalid_review_disposition:{dimension}")
        if disposition == "CONFIRMED" and not _text(review.get("evidence_ref")):
            issues.append(f"{code}:confirmed_dimension_without_evidence:{dimension}")
        if disposition in {"NOT_APPLICABLE", "UNKNOWN"} and not _text(review.get("rationale")):
            issues.append(f"{code}:{disposition.lower()}_dimension_without_rationale:{dimension}")

    checks = case.get("acceptance_checks") if isinstance(case.get("acceptance_checks"), dict) else {}
    for check in plan.get("acceptance_checks", []):
        result = checks.get(check)
        if not isinstance(result, dict) or _text(result.get("status")).upper() != "PASS":
            issues.append(f"{code}:acceptance_check_not_PASS:{check}")
        elif not _text(result.get("evidence_ref")):
            issues.append(f"{code}:acceptance_check_without_evidence:{check}")

    return issues


def evaluate(profile: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    profile_ibge = _text(profile.get("municipality_ibge"))
    plan_ibge = _text(plan.get("municipality_ibge"))
    global_issues: list[str] = []
    if not profile_ibge or profile_ibge != plan_ibge:
        global_issues.append("municipality_identity_mismatch")

    profile_min = int((profile.get("manual_acceptance") or {}).get("test_lots") or 0)
    plan_min = int(plan.get("minimum_cases") or 0)
    minimum = max(profile_min, plan_min, 1)
    cases = plan.get("cases") if isinstance(plan.get("cases"), list) else []

    case_results = []
    for case in cases:
        if not isinstance(case, dict):
            case_results.append({"case_code": None, "status": "BLOCKED", "issues": ["case_not_object"]})
            continue
        issues = _case_issues(case, plan)
        case_results.append({
            "case_code": case.get("case_code"),
            "status": "PASS" if not issues else "BLOCKED",
            "issues": issues,
        })

    unique_codes = [_text(c.get("case_code")) for c in cases if isinstance(c, dict)]
    if len(unique_codes) != len(set(unique_codes)):
        global_issues.append("duplicate_case_code")

    passing = sum(1 for item in case_results if item["status"] == "PASS")
    if len(cases) < minimum:
        status = "PENDING_CASE_SELECTION"
    elif global_issues or passing != len(cases):
        status = "BLOCKED_REVIEW"
    else:
        # A deterministic gate may establish eligibility, never professional/legal homologation itself.
        status = "READY_FOR_PROFESSIONAL_HOMOLOGATION"

    return {
        "municipality_ibge": plan_ibge or profile_ibge,
        "status": status,
        "minimum_cases": minimum,
        "total_cases": len(cases),
        "passing_cases": passing,
        "blocked_cases": len(case_results) - passing,
        "homologation_eligible": status == "READY_FOR_PROFESSIONAL_HOMOLOGATION",
        "production_ready": False,
        "global_issues": global_issues,
        "cases": case_results,
        "policy": {
            "machine_gate_can_homologate": False,
            "professional_review_required": True,
            "all_golden_cases_must_pass": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed municipality golden-lot readiness evaluator")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--require-not-ready", action="store_true")
    args = parser.parse_args()

    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    result = evaluate(profile, plan)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)

    if args.require_ready and not result["homologation_eligible"]:
        return 2
    if args.require_not_ready and result["homologation_eligible"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
