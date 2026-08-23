#!/usr/bin/env bash
set -euo pipefail
command -v k6 >/dev/null || { echo 'k6 is required' >&2;exit 1; }
k6 run -e BASE_URL="${BASE_URL:?BASE_URL required}" ops/load/k6-smoke.js
