#!/usr/bin/env bash
set -euo pipefail

: "${PLATFORM_DB_MIGRATION_USER:=lotediretor}"
: "${PLATFORM_DB_MIGRATION_PASSWORD:=lotediretor_local}"
: "${PLATFORM_DB_NAME:=lotediretor}"
: "${INTERNAL_API_TOKEN:?INTERNAL_API_TOKEN is required}"

BASE_URL="${BASE_URL:-http://localhost:${HTTP_PORT:-8080}}"
TENANT_A='0198f020-0000-7000-8000-000000000001'
TENANT_B='0198f020-0000-7000-8000-000000000002'
ROW_A='0198f020-1000-7000-8000-000000000001'
ROW_B='0198f020-1000-7000-8000-000000000002'
ROW_PUBLIC='0198f020-1000-7000-8000-000000000003'
ROW_FUTURE='0198f020-1000-7000-8000-000000000004'

# OpenSearch itself must be a real reachable service, not a mocked adapter.
curl -fsS --max-time 20 'http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=15s' >/tmp/ld-opensearch-health.json
python3 - <<'PY'
import json
raw=json.load(open('/tmp/ld-opensearch-health.json'))
if raw.get('status') not in {'yellow','green'}:
    raise SystemExit(f"OpenSearch cluster not ready: {raw}")
print('OpenSearch cluster health PASS:',raw.get('status'))
PY

cat >/tmp/ld-ai-runtime-seed.sql <<SQL
INSERT INTO ingest.document_text(
  id,tenant_id,domain,document_id,chunk_index,text_content,document_title,source_locator,
  visibility,knowledge_status,retrieval_allowed,recorded_at,valid_from,indexed_at,index_error,municipality_ibge
) VALUES
  ('$ROW_A','$TENANT_A','runtime-ai','0198f020-2000-7000-8000-000000000001',0,
   'ALFA URBANO coeficiente máximo 3.2 com evidência privada do tenant A.',
   'Runtime private A','runtime://tenant-a/article-1','PRIVATE','CONFIRMED',true,now()-interval '1 day',now()-interval '1 year',NULL,NULL,NULL),
  ('$ROW_B','$TENANT_B','runtime-ai','0198f020-2000-7000-8000-000000000002',0,
   'SEGREDO BETA coeficiente exclusivo 9.9 pertencente somente ao tenant B.',
   'Runtime private B','runtime://tenant-b/article-1','PRIVATE','CONFIRMED',true,now()-interval '1 day',now()-interval '1 year',NULL,NULL,NULL),
  ('$ROW_PUBLIC',NULL,'runtime-ai','0198f020-2000-7000-8000-000000000003',0,
   'GAMA PUBLICO zoneamento municipal de São Paulo com parâmetro oficial de teste 7.7.',
   'Runtime public São Paulo','runtime://public-sp/article-1','PUBLIC','CONFIRMED',true,now()-interval '1 day',now()-interval '1 year',NULL,NULL,'3550308'),
  ('$ROW_FUTURE','$TENANT_A','runtime-ai','0198f020-2000-7000-8000-000000000004',0,
   'FUTURO DELTA regra válida somente a partir do ano 2099 com valor 88.8.',
   'Runtime future rule','runtime://tenant-a/future','PRIVATE','CONFIRMED',true,now()-interval '1 day','2099-01-01T00:00:00Z',NULL,NULL,NULL)
ON CONFLICT(id) DO UPDATE SET
  text_content=excluded.text_content,
  retrieval_allowed=excluded.retrieval_allowed,
  knowledge_status=excluded.knowledge_status,
  recorded_at=excluded.recorded_at,
  valid_from=excluded.valid_from,
  indexed_at=NULL,
  index_error=NULL;
SQL

docker compose exec -T -e PGPASSWORD="$PLATFORM_DB_MIGRATION_PASSWORD" platform-db \
  psql -h 127.0.0.1 -U "$PLATFORM_DB_MIGRATION_USER" -d "$PLATFORM_DB_NAME" -v ON_ERROR_STOP=1 \
  </tmp/ld-ai-runtime-seed.sql

# Wait for the real ai-ingest worker to publish all four rows to OpenSearch.
start=$(date +%s)
while true; do
  indexed=$(docker compose exec -T -e PGPASSWORD="$PLATFORM_DB_MIGRATION_PASSWORD" platform-db \
    psql -h 127.0.0.1 -U "$PLATFORM_DB_MIGRATION_USER" -d "$PLATFORM_DB_NAME" -Atqc \
    "select count(*) from ingest.document_text where id in ('$ROW_A','$ROW_B','$ROW_PUBLIC','$ROW_FUTURE') and indexed_at is not null")
  if [[ "$indexed" == "4" ]]; then break; fi
  if (( $(date +%s)-start > 90 )); then
    docker compose logs --no-color --tail=200 ai-ingest || true
    docker compose exec -T -e PGPASSWORD="$PLATFORM_DB_MIGRATION_PASSWORD" platform-db \
      psql -h 127.0.0.1 -U "$PLATFORM_DB_MIGRATION_USER" -d "$PLATFORM_DB_NAME" -c \
      "select id,indexed_at,index_error from ingest.document_text where id in ('$ROW_A','$ROW_B','$ROW_PUBLIC','$ROW_FUTURE')"
    echo 'Timed out waiting for AI indexer' >&2
    exit 1
  fi
  sleep 2
done

echo 'AI ingest to OpenSearch PASS'

retrieve(){
  local outfile="$1" payload="$2"
  curl -fsS --max-time 20 \
    -H 'content-type: application/json' \
    -H "x-internal-token: $INTERNAL_API_TOKEN" \
    -d "$payload" "$BASE_URL/ai/v1/retrieve" >"$outfile"
}

retrieve /tmp/ld-ai-a.json "{\"tenantId\":\"$TENANT_A\",\"query\":\"ALFA URBANO coeficiente máximo 3.2\",\"scope\":{\"domains\":[\"runtime-ai\"],\"includePublic\":false,\"knowledgeStatuses\":[\"CONFIRMED\"],\"topK\":10}}"
retrieve /tmp/ld-ai-b-leak.json "{\"tenantId\":\"$TENANT_A\",\"query\":\"SEGREDO BETA coeficiente exclusivo 9.9\",\"scope\":{\"domains\":[\"runtime-ai\"],\"includePublic\":false,\"knowledgeStatuses\":[\"CONFIRMED\"],\"topK\":10}}"
retrieve /tmp/ld-ai-public.json "{\"tenantId\":\"$TENANT_A\",\"query\":\"GAMA PUBLICO São Paulo parâmetro 7.7\",\"scope\":{\"domains\":[\"runtime-ai\"],\"includePublic\":true,\"municipalityIbge\":\"3550308\",\"knowledgeStatuses\":[\"CONFIRMED\"],\"topK\":10}}"
retrieve /tmp/ld-ai-future.json "{\"tenantId\":\"$TENANT_A\",\"query\":\"FUTURO DELTA 88.8\",\"scope\":{\"domains\":[\"runtime-ai\"],\"includePublic\":false,\"knowledgeStatuses\":[\"CONFIRMED\"],\"baseDate\":\"2026-08-23\",\"topK\":10}}"

python3 - "$ROW_A" "$ROW_B" "$ROW_PUBLIC" "$ROW_FUTURE" <<'PY'
import json,sys
row_a,row_b,row_public,row_future=sys.argv[1:]

def load(path):
    raw=json.load(open(path))
    if raw.get('status')!='OK': raise AssertionError((path,raw))
    return raw

def ids(raw): return {str(x.get('id')) for x in raw.get('items',[])}

a=load('/tmp/ld-ai-a.json')
if row_a not in ids(a): raise AssertionError(('tenant A evidence missing',a))
if row_b in ids(a): raise AssertionError(('tenant B leaked into tenant A retrieval',a))
if a.get('mode') not in {'lexical_legal_rerank','hybrid_rrf_legal_rerank'}: raise AssertionError(('unexpected retrieval mode',a))

leak=load('/tmp/ld-ai-b-leak.json')
if row_b in ids(leak): raise AssertionError(('cross-tenant lexical leak',leak))
if any('SEGREDO BETA' in str(x.get('text','')) for x in leak.get('items',[])): raise AssertionError(('cross-tenant text leak',leak))

public=load('/tmp/ld-ai-public.json')
if row_public not in ids(public): raise AssertionError(('public municipal evidence missing',public))
if row_b in ids(public): raise AssertionError(('tenant B leaked in public retrieval',public))

future=load('/tmp/ld-ai-future.json')
if row_future in ids(future): raise AssertionError(('future validity rule leaked into 2026 baseDate',future))

print('AI retrieval tenant/public/temporal gates PASS')
PY
