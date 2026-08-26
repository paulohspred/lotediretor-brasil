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
export RESILIENCE_ARTIFACT_DIR="$ARTIFACT_DIR/resilience"
export SECURITY_ARTIFACT_DIR="$ARTIFACT_DIR/security"
export DR_ARTIFACT_DIR="$ARTIFACT_DIR/dr"
mkdir -p "$ARTIFACT_DIR"
GATE_LEDGER="$ARTIFACT_DIR/gate-status.tsv"
printf 'gate\tstatus\tstarted_at_utc\tcompleted_at_utc\tduration_seconds\n' > "$GATE_LEDGER"

for cmd in docker python3 curl; do command -v "$cmd" >/dev/null || { echo "$cmd is required" >&2; exit 1; }; done
docker compose version >/dev/null

run_gate(){
  local gate="$1";shift
  local start_epoch end_epoch start_iso end_iso rc
  start_epoch=$(date +%s)
  start_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "==> gate[$gate] $*"
  if "$@"; then
    rc=0
    end_epoch=$(date +%s);end_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    printf '%s\tPASS\t%s\t%s\t%s\n' "$gate" "$start_iso" "$end_iso" "$((end_epoch-start_epoch))" >> "$GATE_LEDGER"
  else
    rc=$?
    end_epoch=$(date +%s);end_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    printf '%s\tFAIL\t%s\t%s\t%s\n' "$gate" "$start_iso" "$end_iso" "$((end_epoch-start_epoch))" >> "$GATE_LEDGER"
  fi
  return "$rc"
}

record_skipped(){
  local gate="$1" reason="$2" now
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  printf '%s\tSKIPPED\t%s\t%s\t0\t%s\n' "$gate" "$now" "$now" "$reason" >> "$GATE_LEDGER"
}

capture(){
  local status="$1"
  set +e
  mkdir -p "$ARTIFACT_DIR"
  docker compose ps -a > "$ARTIFACT_DIR/compose-ps.txt" 2>&1
  docker compose logs --no-color --timestamps > "$ARTIFACT_DIR/compose.log" 2>&1
  docker system df > "$ARTIFACT_DIR/docker-df.txt" 2>&1
  docker compose images --format json > "$ARTIFACT_DIR/compose-images.jsonl" 2>/dev/null || true
  docker compose exec -T -e PGPASSWORD="$PLATFORM_DB_MIGRATION_PASSWORD" platform-db \
    psql -h 127.0.0.1 -U "$PLATFORM_DB_MIGRATION_USER" -d "$PLATFORM_DB_NAME" -Atqc \
    "select version from public.schema_migrations order by version" > "$ARTIFACT_DIR/platform-migrations.txt" 2>/dev/null || true
  docker compose exec -T -e PGPASSWORD="$CONTROL_DB_MIGRATION_PASSWORD" control-db \
    psql -h 127.0.0.1 -U "$CONTROL_DB_MIGRATION_USER" -d "$CONTROL_DB_NAME" -Atqc \
    "select version from public.schema_migrations order by version" > "$ARTIFACT_DIR/control-migrations.txt" 2>/dev/null || true
  cp /tmp/ld-opensearch-health.json "$ARTIFACT_DIR/opensearch-health.json" 2>/dev/null
  cp /tmp/ld-ai-*.json "$ARTIFACT_DIR/" 2>/dev/null
  cp /tmp/ld-aitec-*.json "$ARTIFACT_DIR/" 2>/dev/null
  printf '{"status":"%s","loadProfile":"%s","timestampUtc":"%s"}\n' "$status" "$PROFILE" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$ARTIFACT_DIR/qualification.json"
  set -e
}

finish(){
  local code=$? status report_rc=0
  trap - EXIT
  status="$([ "$code" -eq 0 ] && echo PASS || echo FAIL)"
  capture "$status"

  python3 ./ops/cortex/qualification-report.py "$ARTIFACT_DIR" "$status" "$PROFILE" || report_rc=$?
  if [[ "$code" -eq 0 && "$report_rc" -ne 0 ]]; then
    echo 'Final qualification report rejected a nominal PASS; marking run FAIL.' >&2
    code=1
    status=FAIL
    capture "$status"
    python3 ./ops/cortex/qualification-report.py "$ARTIFACT_DIR" "$status" "$PROFILE" || true
  fi

  if ! python3 ./ops/cortex/evidence-manifest.py "$ARTIFACT_DIR" "$status" "$PROFILE"; then
    echo 'Evidence manifest generation failed' >&2
    if [[ "$code" -eq 0 ]]; then
      code=1
      status=FAIL
      capture "$status"
    fi
  fi
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

run_gate production_parity sh -c "python3 ops/security/production-parity.py > '$ARTIFACT_DIR/production-parity.json'"
run_gate staging_parity sh -c "python3 ops/staging/production-equivalence.py > '$ARTIFACT_DIR/staging-parity.json'"
run_gate immutable_release sh -c "python3 ops/release/immutable-release.py > '$ARTIFACT_DIR/immutable-release.json'"
run_gate rollback_contract sh -c "bash ops/release/rollback-drill.sh --self-test > '$ARTIFACT_DIR/rollback-contract.txt'"
run_gate compose_model sh -c "docker compose config > '$ARTIFACT_DIR/compose-config.yml'"
run_gate build_images docker compose build

docker compose up -d
run_gate stack_health bash ./ops/runtime/wait-healthy.sh "${CORTEX_HEALTH_TIMEOUT:-480}"
run_gate runtime_smoke bash ./ops/runtime/smoke.sh
run_gate aitec_runtime bash ./ops/aitec/runtime-integration.sh
run_gate rls_isolation bash ./ops/rls/runtime-isolation.sh
run_gate privacy_lgpd bash ./ops/privacy/runtime-integration.sh
run_gate municipality_factory bash ./ops/municipality/factory-runtime.sh
run_gate ai_retrieval bash ./ops/ai/runtime-integration.sh
run_gate critical_fixture_seed bash ./ops/browser/seed-critical-journeys.sh
run_gate browser_critical bash ./ops/browser/run-e2e.sh
run_gate security_baseline bash ./ops/security/runtime-baseline.sh

if [[ "${CORTEX_ZAP:-0}" == "1" ]]; then
  run_gate zap_baseline bash ./ops/security/zap-baseline.sh
else
  record_skipped zap_baseline 'optional external scanner image not requested'
fi

run_gate load_profile env LOAD_PROFILE="$PROFILE" bash ./ops/load/run.sh

if [[ "${CORTEX_FAULT_INJECTION:-1}" == "1" ]]; then
  run_gate fault_injection bash ./ops/resilience/runtime-fault-injection.sh
else
  record_skipped fault_injection 'disabled by CORTEX_FAULT_INJECTION=0; full qualification will be rejected'
fi

run_gate observability bash ./ops/observability/runtime-gate.sh

BACKUP_STAMP="cortex-$STAMP"
run_gate backup bash ./ops/backup/backup.sh "$BACKUP_STAMP"
run_gate restore_dr bash ./ops/backup/restore-drill.sh "$BACKUP_DIR/$BACKUP_STAMP"

echo 'Cortex local qualification gates completed; final report will decide PASS/FAIL.'
