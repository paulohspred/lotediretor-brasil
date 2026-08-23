#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python "$ROOT/ops/municipality/select-golden-lots.py" --ibge 3550308 --limit "${1:-20}" --out "$ROOT/data/municipality-labs/sao-paulo-golden-candidates.runtime.json"
echo "Candidates written. They remain PENDING_HUMAN_REVIEW until official references/parameters are verified."
