#!/usr/bin/env bash
set -euo pipefail

./validate-v19-rc3.sh

if ! command -v docker >/dev/null 2>&1; then
  echo 'Docker unavailable: release gate cannot validate Compose/parity.' >&2
  [[ "${REQUIRE_DOCKER:-true}" == "true" ]] && exit 1
  exit 0
fi

docker compose -f docker-compose.yml config >/dev/null
python3 ops/security/production-parity.py
python3 ops/release/immutable-release.py
bash ops/release/rollback-drill.sh --self-test

if [[ "${RUN_RUNTIME_ACCEPTANCE:-false}" == "true" ]]; then
  ./ops/runtime/acceptance.sh
fi

if [[ "${RUN_CANARY_ACCEPTANCE:-false}" == "true" ]]; then
  : "${CANARY_BASE_URL:?CANARY_BASE_URL is required when RUN_CANARY_ACCEPTANCE=true}"
  : "${CANARY_INTERNAL_API_TOKEN:?CANARY_INTERNAL_API_TOKEN is required when RUN_CANARY_ACCEPTANCE=true}"
  ./ops/release/canary-gate.sh
fi

echo 'Release static/parity/immutable/rollback-contract gate PASS'
