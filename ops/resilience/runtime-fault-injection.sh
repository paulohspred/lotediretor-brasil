#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:${HTTP_PORT:-8080}}"
ARTIFACT_DIR="${RESILIENCE_ARTIFACT_DIR:-runtime-artifacts/resilience}"
mkdir -p "$ARTIFACT_DIR"
: "${INTERNAL_API_TOKEN:?INTERNAL_API_TOKEN is required}"

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
