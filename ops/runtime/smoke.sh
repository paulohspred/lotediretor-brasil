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

# Exercise the Solar 360 v20 plane through the real gateway and the same
# machine-to-machine token used by platform services. The ld-ai-* prefix is
# intentional: runtime-e2e already preserves these JSONs as evidence artifacts.
printf '%-24s ' solar-v20-runtime
curl -fsS --max-time 20 -H "X-Internal-Token: ${INTERNAL_API_TOKEN:?INTERNAL_API_TOKEN required}" \
  "$BASE_URL/solar/v20/capabilities" > /tmp/ld-ai-solar-v20-capabilities.json
curl -fsS --max-time 20 -H "X-Internal-Token: $INTERNAL_API_TOKEN" -H 'Content-Type: application/json' \
  -X POST "$BASE_URL/solar/v20/execute/energy.irradiance" \
  --data '{"kwargs":{"dc_kwp":10,"monthly_poa_kwh_m2":[100,100,100,100,100,100,100,100,100,100,100,100],"loss_fractions":{"temperature":0.02,"soiling":0.02,"shading":0.02,"mismatch":0.02,"wiring":0.02,"inverter":0.02,"availability":0.02}}}' \
  > /tmp/ld-ai-solar-v20-energy.json
python3 - <<'PY'
import json
caps=json.load(open('/tmp/ld-ai-solar-v20-capabilities.json'))
energy=json.load(open('/tmp/ld-ai-solar-v20-energy.json'))
ops={item['operation'] for item in caps['operations']}
required={'source.validate','dsm.roof-surfaces','dsm.obstacles','shadow.project','energy.irradiance','battery.simulate','tariff.apply','connection.precheck','ground-mount.layout','safety.conditioning','calibration.compare','bill.parse-ocr','equipment.snapshot','scene.build','report.build'}
missing=sorted(required-ops)
assert not missing, missing
assert caps['classification']=='PRELIMINARY_ENGINEERING_STUDY'
assert energy['status']=='EXECUTED', energy
assert energy['solver_version']=='solar-scenario-v20.1', energy
assert energy['result']['status']=='CALCULATED_FROM_EXPLICIT_IRRADIANCE_AND_LOSSES', energy
assert energy['result']['annual_net_kwh'] > 0, energy
PY
echo PASS

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
