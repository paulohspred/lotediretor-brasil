#!/usr/bin/env bash
set -euo pipefail
: "${CANARY_BASE_URL:?}"
BASE_URL="$CANARY_BASE_URL" ./ops/runtime/smoke.sh
if command -v k6 >/dev/null; then BASE_URL="$CANARY_BASE_URL" ./ops/load/run.sh; else echo 'k6 unavailable: load gate not executed' >&2; [[ "${REQUIRE_K6:-true}" == "true" ]] && exit 1; fi
echo 'Canary gate PASS'
