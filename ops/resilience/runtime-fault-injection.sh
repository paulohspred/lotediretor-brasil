#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:${HTTP_PORT:-8080}}"
ARTIFACT_DIR="${RESILIENCE_ARTIFACT_DIR:-runtime-artifacts/resilience}"
mkdir -p "$ARTIFACT_DIR"
: "${INTERNAL_API_TOKEN:?INTERNAL_API_TOKEN is required}"
: "${PLATFORM_DB_MIGRATION_USER:=lotediretor}"
: "${PLATFORM_DB_MIGRATION_PASSWORD:=lotediretor_local}"
: "${PLATFORM_DB_NAME:=lotediretor}"

wait_http(){
  local url="$1" timeout="${2:-180}" start
  start=$(date +%s)
  until curl -fsS --max-time 5 "$url" >/dev/null 2>&1; do
    if (( $(date +%s)-start > timeout )); then echo "timeout waiting for $url" >&2; return 1; fi
    sleep 3
  done
}

wait_unavailable(){
  local url="$1" timeout="${2:-30}" start code
  start=$(date +%s)
  while true; do
    code=$(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)
    if [[ "$code" == "000" || "$code" =~ ^5 ]]; then return 0; fi
    if (( $(date +%s)-start > timeout )); then echo "expected $url to become unavailable, got HTTP $code" >&2; return 1; fi
    sleep 1
  done
}

wait_service_healthy(){
  local service="$1" timeout="${2:-180}" start cid status health
  start=$(date +%s)
  while true; do
    cid=$(docker compose ps -q "$service")
    if [[ -n "$cid" ]]; then
      status=$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || true)
      health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$cid" 2>/dev/null || true)
      if [[ "$status" == "running" && ( -z "$health" || "$health" == "healthy" ) ]]; then return 0; fi
    fi
    if (( $(date +%s)-start > timeout )); then docker compose ps "$service" >&2 || true;echo "timeout waiting for service $service" >&2;return 1;fi
    sleep 3
  done
}

platform_sql(){
  docker compose exec -T -e PGPASSWORD="$PLATFORM_DB_MIGRATION_PASSWORD" platform-db \
    psql -h 127.0.0.1 -U "$PLATFORM_DB_MIGRATION_USER" -d "$PLATFORM_DB_NAME" -v ON_ERROR_STOP=1 "$@"
}

platform_scalar(){
  local sql="$1"
  platform_sql -Atqc "$sql"
}

record(){ printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >> "$ARTIFACT_DIR/events.tsv"; }

restart_case(){
  local service="$1" url="$2"
  echo "==> fault: SIGKILL $service"
  docker compose kill -s KILL "$service"
  wait_unavailable "$url" 30
  record "$service" 'unavailable_after_sigkill'
  docker compose up -d "$service"
  wait_service_healthy "$service" 180
  wait_http "$url" 60
  record "$service" 'recovered'
}

# Prove abrupt process death is visible and each API can return to service without
# replacing volumes or weakening authentication/tenant configuration.
restart_case platform-api "$BASE_URL/api/v1/health"
restart_case control-api "$BASE_URL/control/v1/health"
restart_case ai-gateway "$BASE_URL/ai/health"

# Prove the durable A.I TEC queue survives an engine outage. A retryable transport
# failure must schedule a future attempt instead of burning through all attempts in
# a tight poll loop; after engine recovery the same job id must complete exactly once.
AITEC_TENANT='0198f029-0000-7000-8000-000000000001'
AITEC_PROJECT='0198f029-2000-7000-8000-000000000001'
AITEC_JOB='0198f029-3000-7000-8000-000000000001'

echo '==> fault: stop A.I TEC engine before queuing durable job'
docker compose stop aitec-engine
start=$(date +%s)
while docker compose ps --status running --services | grep -qx 'aitec-engine'; do
  if (( $(date +%s)-start > 30 )); then echo 'A.I TEC engine did not stop' >&2;exit 1;fi
  sleep 1
done

platform_sql <<SQL
BEGIN;
DELETE FROM event.outbox WHERE dedupe_key IN ('aitec.job.completed:$AITEC_JOB','aitec.job.failed:$AITEC_JOB');
DELETE FROM aitec.job WHERE id='$AITEC_JOB';
INSERT INTO aitec.project(id,tenant_id,name,status)
VALUES('$AITEC_PROJECT','$AITEC_TENANT','Synthetic resilience A.I TEC project','DRAFT')
ON CONFLICT(id) DO UPDATE SET tenant_id=excluded.tenant_id,name=excluded.name,status='DRAFT';
INSERT INTO aitec.job(
  id,tenant_id,project_id,operation,args,kwargs,execution_context,status,attempts,next_attempt_at,created_by
) VALUES(
  '$AITEC_JOB','$AITEC_TENANT','$AITEC_PROJECT','terrain.tin','[]'::jsonb,
  '{"samples":[{"x":0,"y":0,"z":100},{"x":10,"y":0,"z":101},{"x":0,"y":10,"z":102},{"x":10,"y":10,"z":103}]}'::jsonb,
  '{"tenant_id":"$AITEC_TENANT","project_id":"$AITEC_PROJECT","seed":42}'::jsonb,
  'QUEUED',0,now(),'resilience-fixture'
);
COMMIT;
SQL

start=$(date +%s)
while true; do
  state=$(platform_scalar "select status||'|'||attempts||'|'||(next_attempt_at>now())||'|'||coalesce(error,'') from aitec.job where id='$AITEC_JOB'")
  IFS='|' read -r status attempts future error <<<"$state"
  if [[ "$status" == 'QUEUED' && "$attempts" == '1' && "$future" == 't' && "$error" == aitec_engine_unreachable:* ]]; then
    break
  fi
  if [[ "$status" == 'FAILED' || "$attempts" =~ ^[2-9][0-9]*$ ]]; then
    echo "A.I TEC retry hot-looped or terminated during outage: $state" >&2
    exit 1
  fi
  if (( $(date +%s)-start > 30 )); then
    echo "timeout waiting for scheduled A.I TEC retry; last=$state" >&2
    docker compose logs --no-color --tail=200 aitec-worker >&2 || true
    exit 1
  fi
  sleep 0.2
done
record aitec-engine 'retry_scheduled_without_hot_loop'

echo '==> recover A.I TEC engine and wait for same durable job'
docker compose up -d aitec-engine
wait_service_healthy aitec-engine 180
wait_http "$BASE_URL/aitec/health" 60
start=$(date +%s)
while true; do
  state=$(platform_scalar "select status||'|'||attempts||'|'||coalesce(solver_version,'')||'|'||coalesce(classification,'')||'|'||coalesce(professional_review_required::text,'') from aitec.job where id='$AITEC_JOB'")
  IFS='|' read -r status attempts solver classification review <<<"$state"
  if [[ "$status" == 'COMPLETED' ]]; then break; fi
  if [[ "$status" == 'FAILED' || "$status" == 'CANCELLED' ]]; then
    echo "A.I TEC durable job failed after engine recovery: $state" >&2
    exit 1
  fi
  if (( $(date +%s)-start > 90 )); then
    echo "timeout waiting for A.I TEC durable job recovery; last=$state" >&2
    docker compose logs --no-color --tail=200 aitec-worker aitec-engine >&2 || true
    exit 1
  fi
  sleep 1
done

[[ "$attempts" == '2' ]] || { echo "expected exactly 2 A.I TEC attempts, got $attempts" >&2; exit 1; }
[[ "$solver" == 'aitec-terrain-v20.1' ]] || { echo "unexpected A.I TEC solver after recovery: $solver" >&2; exit 1; }
[[ "$classification" == 'STUDY_PREPROJECT_NOT_EXECUTIVE' ]] || { echo "classification lost after retry: $classification" >&2; exit 1; }
[[ "$review" == 'true' ]] || { echo "professional review flag lost after retry: $review" >&2; exit 1; }
completion_events=$(platform_scalar "select count(*) from event.outbox where dedupe_key='aitec.job.completed:$AITEC_JOB'")
[[ "$completion_events" == '1' ]] || { echo "expected one A.I TEC completion event, got $completion_events" >&2; exit 1; }

platform_sql -Atqc "select json_build_object(
  'id',id,'status',status,'attempts',attempts,'solverVersion',solver_version,
  'classification',classification,'professionalReviewRequired',professional_review_required,
  'nextAttemptAt',next_attempt_at,'completedAt',completed_at,
  'triangleCount',coalesce((engine_response#>>'{result,triangle_count}')::int,0),
  'completionEvents',$completion_events
)::text from aitec.job where id='$AITEC_JOB'" > "$ARTIFACT_DIR/aitec-engine-outage-job.json"
python3 - "$ARTIFACT_DIR/aitec-engine-outage-job.json" <<'PY'
import json,sys
raw=json.load(open(sys.argv[1]))
assert raw['status']=='COMPLETED',raw
assert raw['attempts']==2,raw
assert raw['triangleCount']>=2,raw
assert raw['completionEvents']==1,raw
PY
record aitec-engine 'recovered_same_job_completed_once'

# Prove the retrieval plane fails closed when OpenSearch disappears. A 5xx is
# acceptable; a structured 200 is acceptable only when it returns no evidence
# and explicitly records retrieval errors. Returning evidence from stale/foreign
# state while the search backend is absent is a gate failure.
echo '==> fault: stop OpenSearch'
docker compose stop opensearch
start=$(date +%s)
while curl -fsS --max-time 2 http://localhost:9200/ >/dev/null 2>&1; do
  if (( $(date +%s)-start > 30 )); then echo 'OpenSearch did not stop' >&2;exit 1;fi
  sleep 1
done

OUT="$ARTIFACT_DIR/opensearch-outage-retrieve.json"
HTTP_CODE=$(curl -sS --max-time 20 -o "$OUT" -w '%{http_code}' \
  -H 'content-type: application/json' -H "x-internal-token: $INTERNAL_API_TOKEN" \
  -d '{"tenantId":"0198f020-0000-7000-8000-000000000001","query":"ALFA URBANO coeficiente máximo 3.2","scope":{"domains":["runtime-ai"],"includePublic":false,"knowledgeStatuses":["CONFIRMED"],"topK":10}}' \
  "$BASE_URL/ai/v1/retrieve" || true)
if [[ "$HTTP_CODE" == "200" ]]; then
  python3 - "$OUT" <<'PY'
import json,sys
raw=json.load(open(sys.argv[1]))
items=raw.get('items') or []
errors=raw.get('errors') or []
mode=str(raw.get('mode') or '').lower()
if items:
    raise SystemExit(f'OpenSearch outage returned evidence instead of failing closed: {raw}')
if not errors and mode not in {'error','degraded','unavailable'}:
    raise SystemExit(f'OpenSearch outage returned ambiguous success without explicit degradation: {raw}')
PY
elif [[ ! "$HTTP_CODE" =~ ^5 ]]; then
  echo "unexpected retrieval status during OpenSearch outage: HTTP $HTTP_CODE" >&2
  cat "$OUT" >&2 || true
  exit 1
fi
record opensearch "retrieval_fail_closed_http_${HTTP_CODE}"

echo '==> recover OpenSearch and retrieval plane'
docker compose up -d opensearch ai-gateway ai-ingest
wait_service_healthy opensearch 240
wait_service_healthy ai-gateway 120
wait_http 'http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=10s' 120
./ops/ai/runtime-integration.sh
record opensearch 'recovered_and_retrieval_reproved'

# Final full smoke ensures the rest of the edge recovered after all injected faults.
./ops/runtime/smoke.sh
record runtime 'final_smoke_pass'
echo "Runtime fault injection PASS; evidence: $ARTIFACT_DIR"
