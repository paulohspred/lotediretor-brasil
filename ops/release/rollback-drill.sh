#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

IMAGE_VARS=(
  PLATFORM_API_IMAGE CONTROL_API_IMAGE AI_GATEWAY_IMAGE SOLAR_ENGINE_IMAGE AITEC_ENGINE_IMAGE
  EVENT_DISPATCHER_IMAGE GEO_WORKER_IMAGE DOCUMENT_WORKER_IMAGE REPORT_WORKER_IMAGE
  RURAL_MONITOR_WORKER_IMAGE RURAL_EXPORT_WORKER_IMAGE BILLING_WORKER_IMAGE DATA_PIPELINES_IMAGE
  AI_INGEST_IMAGE SITE_WEB_IMAGE CLIENT_WEB_IMAGE ADMIN_WEB_IMAGE
)

usage(){
  cat <<'EOF'
Usage:
  ops/release/rollback-drill.sh --self-test
  ops/release/rollback-drill.sh CANDIDATE.env PREVIOUS.env

By default the second form performs a non-mutating render/contract validation.
Set ROLLBACK_EXECUTE=true only in an isolated staging/qualification environment
to deploy candidate -> smoke -> previous digest -> smoke.

The env files must contain every *_IMAGE variable as repository@sha256:<64 hex>.
Runtime secrets/DB credentials are supplied separately by the environment.
EOF
}

write_fixture_env(){
  local path="$1" suffix="$2" first_digest="$3"
  : >"$path"
  local i=0 digest repo
  for key in "${IMAGE_VARS[@]}"; do
    i=$((i+1))
    if [[ "$i" -eq 1 ]]; then digest="$first_digest"; else digest="$(printf '%064x' "$((i+suffix))")"; fi
    repo="ghcr.io/lotediretor/${key,,}"
    printf '%s=%s@sha256:%s\n' "$key" "$repo" "$digest" >>"$path"
  done
}

if [[ "${1:-}" == "--self-test" ]]; then
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  write_fixture_env "$tmp/candidate.env" 100 "$(printf '%064x' 9001)"
  write_fixture_env "$tmp/previous.env" 200 "$(printf '%064x' 8001)"
  ROLLBACK_SELF_TEST=1 ROLLBACK_EXECUTE=false "$0" "$tmp/candidate.env" "$tmp/previous.env"
  echo 'Rollback drill self-test PASS'
  exit 0
fi

[[ $# -eq 2 ]] || { usage >&2; exit 2; }
CANDIDATE_ENV="$1"; PREVIOUS_ENV="$2"
[[ -f "$CANDIDATE_ENV" ]] || { echo "candidate env not found: $CANDIDATE_ENV" >&2; exit 2; }
[[ -f "$PREVIOUS_ENV" ]] || { echo "previous env not found: $PREVIOUS_ENV" >&2; exit 2; }

# Safe fixtures are used only by the CI self-test/render path. A real execution
# must pass production-like values and pass the production preflight.
if [[ "${ROLLBACK_SELF_TEST:-0}" == "1" ]]; then
  export PUBLIC_DOMAIN="${PUBLIC_DOMAIN:-app.example.com}" AUTH_DOMAIN="${AUTH_DOMAIN:-auth.example.com}" ACME_EMAIL="${ACME_EMAIL:-ops@example.com}"
  export KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-release-ci}" KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-release-keycloak-fixture-2026}"
  export INTERNAL_API_TOKEN="${INTERNAL_API_TOKEN:-release-internal-fixture-2026}" OIDC_CLIENT_SECRET="${OIDC_CLIENT_SECRET:-release-oidc-fixture-2026}"
  export PLATFORM_DB_MIGRATION_USER="${PLATFORM_DB_MIGRATION_USER:-ld_platform_migration}" PLATFORM_DB_MIGRATION_PASSWORD="${PLATFORM_DB_MIGRATION_PASSWORD:-release-platform-owner-2026}" PLATFORM_DB_NAME="${PLATFORM_DB_NAME:-lotediretor}"
  export PLATFORM_DB_APP_USER="${PLATFORM_DB_APP_USER:-ld_platform_app}" PLATFORM_DB_APP_PASSWORD="${PLATFORM_DB_APP_PASSWORD:-release-platform-app-2026}" PLATFORM_DB_TILES_USER="${PLATFORM_DB_TILES_USER:-ld_tiles}" PLATFORM_DB_TILES_PASSWORD="${PLATFORM_DB_TILES_PASSWORD:-release-tiles-2026}"
  export PLATFORM_DB_EVENT_PASSWORD="${PLATFORM_DB_EVENT_PASSWORD:-release-event-2026}" PLATFORM_DB_WORKER_PASSWORD="${PLATFORM_DB_WORKER_PASSWORD:-release-worker-2026}"
  export CONTROL_DB_MIGRATION_USER="${CONTROL_DB_MIGRATION_USER:-ld_control_migration}" CONTROL_DB_MIGRATION_PASSWORD="${CONTROL_DB_MIGRATION_PASSWORD:-release-control-owner-2026}" CONTROL_DB_NAME="${CONTROL_DB_NAME:-lotediretor_control}"
  export CONTROL_DB_APP_USER="${CONTROL_DB_APP_USER:-ld_control_app}" CONTROL_DB_APP_PASSWORD="${CONTROL_DB_APP_PASSWORD:-release-control-app-2026}" CONTROL_DB_WORKER_PASSWORD="${CONTROL_DB_WORKER_PASSWORD:-release-control-worker-2026}"
  export S3_ACCESS_KEY="${S3_ACCESS_KEY:-ld-object}" S3_SECRET_KEY="${S3_SECRET_KEY:-release-object-2026}"
elif [[ "${ROLLBACK_EXECUTE:-false}" == "true" ]]; then
  ./ops/runtime/production-preflight.sh
fi

validate_env(){
  local file="$1"
  python3 - "$file" "${IMAGE_VARS[@]}" <<'PY'
import re,sys
from pathlib import Path
p=Path(sys.argv[1]);keys=sys.argv[2:]
values={}
for raw in p.read_text().splitlines():
    line=raw.strip()
    if not line or line.startswith('#'): continue
    if '=' not in line: raise SystemExit(f'invalid env line: {raw!r}')
    k,v=line.split('=',1);values[k]=v
pat=re.compile(r'^.+@sha256:[0-9a-fA-F]{64}$')
missing=[k for k in keys if not pat.match(values.get(k,''))]
if missing: raise SystemExit(f'missing/non-immutable image values in {p}: {missing}')
print(f'{p}: immutable image contract PASS ({len(keys)} images)')
PY
}
validate_env "$CANDIDATE_ENV"
validate_env "$PREVIOUS_ENV"

ARTIFACT_DIR="${ROLLBACK_ARTIFACT_DIR:-runtime-artifacts/release/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$ARTIFACT_DIR"
render(){
  local envfile="$1" outfile="$2"
  docker compose --env-file "$envfile" \
    -f docker-compose.yml -f docker-compose.production.yml -f docker-compose.release.yml \
    --profile full --profile ops config --format json >"$outfile"
}
render "$CANDIDATE_ENV" "$ARTIFACT_DIR/candidate-compose.json"
render "$PREVIOUS_ENV" "$ARTIFACT_DIR/previous-compose.json"

python3 - "$ARTIFACT_DIR/candidate-compose.json" "$ARTIFACT_DIR/previous-compose.json" <<'PY'
import json,sys
c=json.load(open(sys.argv[1]));p=json.load(open(sys.argv[2]))
def images(m): return {k:v.get('image') for k,v in (m.get('services') or {}).items() if v.get('image')}
ci,pi=images(c),images(p)
managed=[k for k in ci if k in pi and str(ci[k]).startswith('ghcr.io/lotediretor/')]
changed=[k for k in managed if ci[k]!=pi[k]]
if not changed: raise SystemExit('candidate and previous release contain no changed managed image digest')
for m,label in ((c,'candidate'),(p,'previous')):
    for name,svc in (m.get('services') or {}).items():
        image=svc.get('image')
        if image and str(image).startswith('ghcr.io/lotediretor/') and '@sha256:' not in str(image):
            raise SystemExit(f'{label}:{name} is mutable: {image}')
print('Rollback render comparison PASS; changed services:',','.join(sorted(changed)))
PY

if [[ "${ROLLBACK_EXECUTE:-false}" != "true" ]]; then
  echo "Rollback contract PASS (non-mutating). Artifacts: $ARTIFACT_DIR"
  exit 0
fi

: "${COMPOSE_PROJECT_NAME:=lotediretor_rollback_drill}"
export COMPOSE_PROJECT_NAME
export COMPOSE_FILE="docker-compose.yml:docker-compose.production.yml:docker-compose.release.yml"
export COMPOSE_PROFILES="full,ops"

# Preserve a recoverable baseline before candidate migration/start. We never run
# automatic down migrations or a destructive restore in this drill.
BACKUP_DIR="${BACKUP_DIR:-$ARTIFACT_DIR/backups}" ./ops/backup/backup.sh "pre-candidate"

echo '==> Deploy immutable candidate'
docker compose --env-file "$CANDIDATE_ENV" pull
docker compose --env-file "$CANDIDATE_ENV" up -d --remove-orphans
./ops/runtime/wait-healthy.sh "${ROLLBACK_HEALTH_TIMEOUT:-480}"
./ops/runtime/smoke.sh

echo '==> Roll back to immutable previous digests'
docker compose --env-file "$PREVIOUS_ENV" pull
docker compose --env-file "$PREVIOUS_ENV" up -d --remove-orphans
./ops/runtime/wait-healthy.sh "${ROLLBACK_HEALTH_TIMEOUT:-480}"
./ops/runtime/smoke.sh

docker compose ps -a >"$ARTIFACT_DIR/compose-ps-after-rollback.txt"
printf '{"status":"PASS","candidate":"%s","previous":"%s","automaticDownMigration":false,"automaticRestore":false}\n' "$CANDIDATE_ENV" "$PREVIOUS_ENV" >"$ARTIFACT_DIR/rollback-result.json"
echo "Rollback execution PASS. Artifacts: $ARTIFACT_DIR"
