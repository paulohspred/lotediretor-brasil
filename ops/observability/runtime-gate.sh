#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACT_DIR="${OBSERVABILITY_ARTIFACT_DIR:-$ROOT_DIR/runtime-artifacts/observability}"
mkdir -p "$ARTIFACT_DIR"
OUT="$ARTIFACT_DIR/observability-gate.json"

for service in prometheus grafana loki tempo promtail alertmanager otel-collector; do
  if ! docker compose ps --status running --services | grep -qx "$service"; then
    echo "observability service not running: $service" >&2
    echo "Start Compose with COMPOSE_PROFILES=full,ops" >&2
    exit 1
  fi
done

docker compose exec -T aitec-engine python - <<'PY' > "$OUT"
import json,time,urllib.request

checks={
  'prometheus':'http://prometheus:9090/-/ready',
  'grafana':'http://grafana:3000/api/health',
  'loki':'http://loki:3100/ready',
  'tempo':'http://tempo:3200/ready',
  'promtail':'http://promtail:9080/ready',
  'alertmanager':'http://alertmanager:9093/-/ready',
  'otel-collector':'http://otel-collector:13133/',
}

def get(url,timeout=5):
    req=urllib.request.Request(url,headers={'User-Agent':'lotediretor-observability-gate'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        body=r.read().decode('utf-8','replace')
        if not (200 <= r.status < 300):
            raise RuntimeError(f'{url}:HTTP {r.status}')
        return body

results={}
deadline=time.time()+120
pending=dict(checks)
while pending and time.time()<deadline:
    for name,url in list(pending.items()):
        try:
            body=get(url)
            results[name]={'status':'UP','sample':body[:200]}
            pending.pop(name,None)
        except Exception as exc:
            results[name]={'status':'WAITING','error':str(exc)[:300]}
    if pending:time.sleep(3)
if pending:
    raise RuntimeError('observability_not_ready:'+','.join(sorted(pending)))

targets=json.loads(get('http://prometheus:9090/api/v1/targets'))
active=targets.get('data',{}).get('activeTargets',[])
required={'platform-api','control-api','solar-engine','aitec-engine'}
by_pool={}
for target in active:
    pool=target.get('scrapePool')
    if pool in required:
        by_pool[pool]={
            'health':target.get('health'),
            'lastError':target.get('lastError') or '',
            'scrapeUrl':target.get('scrapeUrl'),
        }
missing=sorted(required-set(by_pool))
down=sorted(name for name,item in by_pool.items() if item['health']!='up' or item['lastError'])
if missing:raise RuntimeError('prometheus_targets_missing:'+','.join(missing))
if down:raise RuntimeError('prometheus_targets_down:'+','.join(down))

rules=json.loads(get('http://prometheus:9090/api/v1/rules'))
rule_names=[]
for group in rules.get('data',{}).get('groups',[]):
    for rule in group.get('rules',[]):
        if rule.get('name'):rule_names.append(rule['name'])
required_rules={'LoteDiretorServiceDown','LoteDiretorTargetMissing'}
missing_rules=sorted(required_rules-set(rule_names))
if missing_rules:raise RuntimeError('prometheus_rules_missing:'+','.join(missing_rules))

print(json.dumps({
  'status':'PASS',
  'components':results,
  'prometheusTargets':by_pool,
  'alertRules':sorted(set(rule_names)),
},sort_keys=True))
PY

cat "$OUT"
echo "Observability runtime gate PASS"
