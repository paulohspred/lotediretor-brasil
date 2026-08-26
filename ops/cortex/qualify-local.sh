#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PROFILE="${1:-${CORTEX_LOAD_PROFILE:-ci}}"
case "$PROFILE" in ci|soak|capacity) ;; *) echo "usage: $0 [ci|soak|capacity]" >&2; exit 2;; esac

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-lotediretor_cortex}"
export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml:docker-compose.ci.yml:docker-compose.ops.yml}"
export COMPOSE_PROFILES="${COMPOSE_PROFILES:-full,ops}"
export COMPOSE_PARALLEL_LIMIT="${COMPOSE_PARALLEL_LIMIT:-2}"
export HTTP_PORT="${HTTP_PORT:-8080}"
export PLATFORM_DB_MIGRATION_USER="${PLATFORM_DB_MIGRATION_USER:-lotediretor}"
export PLATFORM_DB_MIGRATION_PASSWORD="${PLATFORM_DB_MIGRATION_PASSWORD:-cortex-platform-owner-local}"
export PLATFORM_DB_NAME="${PLATFORM_DB_NAME:-lotediretor}"
export PLATFORM_DB_APP_USER="${PLATFORM_DB_APP_USER:-lotediretor_app}"
export PLATFORM_DB_APP_PASSWORD="${PLATFORM_DB_APP_PASSWORD:-cortex-platform-app-local}"
export PLATFORM_DB_TILES_USER="${PLATFORM_DB_TILES_USER:-lotediretor_tiles}"
export PLATFORM_DB_TILES_PASSWORD="${PLATFORM_DB_TILES_PASSWORD:-cortex-platform-tiles-local}"
export PLATFORM_DB_EVENT_PASSWORD="${PLATFORM_DB_EVENT_PASSWORD:-cortex-platform-event-local}"
export PLATFORM_DB_WORKER_PASSWORD="${PLATFORM_DB_WORKER_PASSWORD:-cortex-platform-worker-local}"
export CONTROL_DB_MIGRATION_USER="${CONTROL_DB_MIGRATION_USER:-lotediretor_control}"
export CONTROL_DB_MIGRATION_PASSWORD="${CONTROL_DB_MIGRATION_PASSWORD:-cortex-control-owner-local}"
export CONTROL_DB_NAME="${CONTROL_DB_NAME:-lotediretor_control}"
export CONTROL_DB_APP_USER="${CONTROL_DB_APP_USER:-lotediretor_control_app}"
export CONTROL_DB_APP_PASSWORD="${CONTROL_DB_APP_PASSWORD:-cortex-control-app-local}"
export CONTROL_DB_WORKER_PASSWORD="${CONTROL_DB_WORKER_PASSWORD:-cortex-control-worker-local}"
export S3_ACCESS_KEY="${S3_ACCESS_KEY:-lotediretor_cortex}"
export S3_SECRET_KEY="${S3_SECRET_KEY:-cortex-object-storage-local}"
export S3_BUCKET="${S3_BUCKET:-lotediretor-cortex}"
export INTERNAL_API_TOKEN="${INTERNAL_API_TOKEN:-cortex-internal-api-token-local}"
export KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-cortex-admin}"
export KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-cortex-keycloak-admin-local}"
export OIDC_CLIENT_ID="${OIDC_CLIENT_ID:-lotediretor-app}"
# Must match infra/keycloak/realm-lotediretor.json for the local imported realm.
export OIDC_CLIENT_SECRET="${OIDC_CLIENT_SECRET:-local-lotediretor-secret}"
export SESSION_COOKIE_SECURE="${SESSION_COOKIE_SECURE:-false}"
export ALLOW_LOCAL_AUTO_MEMBERSHIP="${ALLOW_LOCAL_AUTO_MEMBERSHIP:-true}"
export GRAFANA_ADMIN_USER="${GRAFANA_ADMIN_USER:-cortex-admin}"
export GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-cortex-grafana-admin-local}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARTIFACT_DIR="${CORTEX_ARTIFACT_DIR:-$ROOT_DIR/runtime-artifacts/cortex/$STAMP}"
export BACKUP_DIR="${BACKUP_DIR:-$ARTIFACT_DIR/backups}"
export BROWSER_ARTIFACT_DIR="$ARTIFACT_DIR/browser"
export LOAD_ARTIFACT_DIR="$ARTIFACT_DIR/load"
export OBSERVABILITY_ARTIFACT_DIR="$ARTIFACT_DIR/observability"
mkdir -p "$ARTIFACT_DIR"

for cmd in docker python3; do command -v "$cmd" >/dev/null || { echo "$cmd is required" >&2; exit 1; }; done
docker compose version >/dev/null

capture(){
  local status="$1"
  set +e
  mkdir -p "$ARTIFACT_DIR"
  docker compose ps -a > "$ARTIFACT_DIR/compose-ps.txt" 2>&1
  docker compose logs --no-color --timestamps > "$ARTIFACT_DIR/compose.log" 2>&1
  docker system df > "$ARTIFACT_DIR/docker-df.txt" 2>&1
  cp /tmp/ld-opensearch-health.json "$ARTIFACT_DIR/opensearch-health.json" 2>/dev/null
  cp /tmp/ld-ai-*.json "$ARTIFACT_DIR/" 2>/dev/null
  cp /tmp/ld-aitec-*.json "$ARTIFACT_DIR/" 2>/dev/null
  printf '{"status":"%s","loadProfile":"%s","timestampUtc":"%s"}\n' "$status" "$PROFILE" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$ARTIFACT_DIR/qualification.json"
  set -e
}

finish(){
  local code=$?
  trap - EXIT
  capture "$([ "$code" -eq 0 ] && echo PASS || echo FAIL)"
  echo "Cortex qualification artifacts: $ARTIFACT_DIR"
  if [[ "${CORTEX_KEEP_STACK:-1}" == "1" ]]; then
    echo "Stack left running for inspection (CORTEX_KEEP_STACK=0 to auto-teardown)."
    echo "Gateway: http://127.0.0.1:$HTTP_PORT"
    echo "Keycloak: http://127.0.0.1:8081"
    echo "Prometheus: http://127.0.0.1:${PROMETHEUS_PORT:-9090}"
    echo "Grafana: http://127.0.0.1:${GRAFANA_PORT:-3005}"
  else
    docker compose down -v --remove-orphans || true
  fi
  exit "$code"
}
trap finish EXIT

if [[ "${CORTEX_RESET:-1}" == "1" ]]; then
  docker compose down -v --remove-orphans || true
fi

echo '==> Validate Compose model'
docker compose config > "$ARTIFACT_DIR/compose-config.yml"

echo '==> Build application images'
docker compose build

echo '==> Start full + observability stack'
docker compose up -d
bash ./ops/runtime/wait-healthy.sh "${CORTEX_HEALTH_TIMEOUT:-480}"

echo '==> Gateway/service smoke'
bash ./ops/runtime/smoke.sh

echo '==> A.I TEC advanced runtime'
bash ./ops/aitec/runtime-integration.sh

echo '==> Cross-tenant RLS isolation'
bash ./ops/rls/runtime-isolation.sh

echo '==> Privacy/LGPD RLS, legal hold and retention guards'
bash ./ops/privacy/runtime-integration.sh

echo '==> Municipality Factory guards/RLS'
bash ./ops/municipality/factory-runtime.sh

echo '==> OpenSearch AI ingest/retrieval isolation'
bash ./ops/ai/runtime-integration.sh

echo '==> Browser/OIDC/mobile/a11y'
bash ./ops/browser/run-e2e.sh

echo '==> Observability stack and Prometheus targets'
bash ./ops/observability/runtime-gate.sh

echo "==> Load profile: $PROFILE"
LOAD_PROFILE="$PROFILE" bash ./ops/load/run.sh

echo '==> Backup/restore drill'
BACKUP_STAMP="cortex-$STAMP"
bash ./ops/backup/backup.sh "$BACKUP_STAMP"
bash ./ops/backup/restore-drill.sh "$BACKUP_DIR/$BACKUP_STAMP"

echo 'Cortex local qualification PASS'
