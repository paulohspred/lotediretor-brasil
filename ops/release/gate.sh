#!/usr/bin/env bash
set -euo pipefail
./validate-v19-rc3.sh
if command -v docker >/dev/null 2>&1; then
  docker compose -f docker-compose.yml config >/dev/null
  if [[ "${RUN_RUNTIME_ACCEPTANCE:-false}" == "true" ]]; then ./ops/runtime/acceptance.sh; fi
else
  echo 'Docker unavailable: runtime acceptance NOT executed' >&2
  [[ "${REQUIRE_DOCKER:-false}" == "true" ]] && exit 1
fi
