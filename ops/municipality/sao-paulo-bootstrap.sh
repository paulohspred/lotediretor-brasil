#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python "$ROOT/workers/data-pipelines/municipality_lab.py" --profile "$ROOT/data/municipality-labs/sao-paulo-3550308.json" bootstrap
