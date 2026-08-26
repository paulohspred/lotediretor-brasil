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
python3 ops/staging/production-equivalence.py
python3 ops/release/immutable-release.py
bash ops/release/rollback-drill.sh --self-test
bash ops/release/verify-signatures.sh --self-test

DEPLOY_ENVIRONMENT="${DEPLOY_ENVIRONMENT:-local}"
VERIFY_RELEASE_SIGNATURES="${VERIFY_RELEASE_SIGNATURES:-false}"
case "$DEPLOY_ENVIRONMENT" in
  staging|production)
    if [[ "$VERIFY_RELEASE_SIGNATURES" != "true" ]]; then
      echo "DEPLOY_ENVIRONMENT=$DEPLOY_ENVIRONMENT requires VERIFY_RELEASE_SIGNATURES=true" >&2
      exit 1
    fi
    ;;
esac

if [[ "$VERIFY_RELEASE_SIGNATURES" == "true" ]]; then
  bash ops/release/verify-signatures.sh
fi

if [[ "${RUN_RUNTIME_ACCEPTANCE:-false}" == "true" ]]; then
  ./ops/runtime/acceptance.sh
fi

if [[ "${RUN_CANARY_ACCEPTANCE:-false}" == "true" ]]; then
  : "${CANARY_BASE_URL:?CANARY_BASE_URL is required when RUN_CANARY_ACCEPTANCE=true}"
  : "${CANARY_INTERNAL_API_TOKEN:?CANARY_INTERNAL_API_TOKEN is required when RUN_CANARY_ACCEPTANCE=true}"
  ./ops/release/canary-gate.sh
fi

echo 'Release static/parity/immutable/signature/rollback-contract gate PASS'
