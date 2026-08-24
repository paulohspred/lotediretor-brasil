#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:${HTTP_PORT:-8080}}"

check(){
  local name="$1" url="$2"
  printf '%-24s ' "$name"
  if curl -fsS --max-time 15 "$url" >/tmp/ld-smoke-body 2>/tmp/ld-smoke-err; then
    echo PASS
  else
    echo FAIL
    cat /tmp/ld-smoke-err
    return 1
  fi
}

check gateway "$BASE_URL/"
check platform-health "$BASE_URL/api/v1/health"
check control-health "$BASE_URL/control/v1/health"
check ai-health "$BASE_URL/ai/health"
check solar-health "$BASE_URL/solar/health"
check aitec-health "$BASE_URL/aitec/health"

# Direct service ports are intentionally not published at the host edge.
# Inspect Docker state/health for every service participating in this Compose run.
docker compose ps -a --format json > /tmp/ld-compose-ps.json
python3 - <<'PY'
import json
import pathlib

p = pathlib.Path('/tmp/ld-compose-ps.json')
text = p.read_text().strip() if p.exists() else ''
if not text:
    raise SystemExit('compose-status            FAIL (no compose services found)')

if text.startswith('['):
    rows = json.loads(text)
else:
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]

one_shot = {
    'minio-init',
    'platform-migrate',
    'control-migrate',
    'platform-db-role-init',
}

bad = []
for row in rows:
    service = row.get('Service') or row.get('Name') or 'unknown'
    state = str(row.get('State') or '').lower()
    health = str(row.get('Health') or '').lower()
    exit_code = row.get('ExitCode')

    if service in one_shot:
        if state in {'exited', 'stopped'}:
            try:
                code = int(exit_code or 0)
            except (TypeError, ValueError):
                code = 1
            if code != 0:
                bad.append((service, state, health, code))
        elif state and state != 'running':
            bad.append((service, state, health, exit_code))
        continue

    if state != 'running':
        bad.append((service, state, health, exit_code))
    elif health and health != 'healthy':
        bad.append((service, state, health, exit_code))

print('compose-status            ' + ('PASS' if not bad else 'FAIL'))
if bad:
    print(bad)
    raise SystemExit(1)
PY
