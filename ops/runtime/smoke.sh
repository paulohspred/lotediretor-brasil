#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:${HTTP_PORT:-8080}}"
check(){
  local name="$1" url="$2"
  printf '%-24s ' "$name"
  if curl -fsS --max-time 10 "$url" >/tmp/ld-smoke-body 2>/tmp/ld-smoke-err; then echo PASS; else echo FAIL; cat /tmp/ld-smoke-err; return 1; fi
}
check gateway "$BASE_URL/"
check platform-health "$BASE_URL/api/v1/health"
# The following direct containers are intentionally not published at the host edge.
# Their Docker healthchecks are inspected instead.
docker compose ps --format json > /tmp/ld-compose-ps.json || true
python3 - <<'PY'
import json, pathlib, sys
p=pathlib.Path('/tmp/ld-compose-ps.json')
if not p.exists() or not p.read_text().strip():
    print('compose-status            SKIP (docker compose status unavailable)')
    raise SystemExit(0)
text=p.read_text().strip()
rows=[]
try:
    if text.startswith('['): rows=json.loads(text)
    else: rows=[json.loads(x) for x in text.splitlines() if x.strip()]
except Exception as e:
    print('compose-status            WARN',e);raise SystemExit(0)
bad=[]
for r in rows:
    service=r.get('Service') or r.get('Name')
    state=(r.get('State') or '').lower(); health=(r.get('Health') or '').lower()
    if state and state!='running' and service not in {'minio-init','platform-migrate','control-migrate'}:bad.append((service,state,health))
    if health and health not in {'healthy',''}:bad.append((service,state,health))
print('compose-status            '+('PASS' if not bad else 'FAIL'))
if bad:
    print(bad);raise SystemExit(1)
PY
