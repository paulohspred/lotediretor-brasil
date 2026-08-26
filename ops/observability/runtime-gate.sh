#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACT_DIR="${OBSERVABILITY_ARTIFACT_DIR:-$ROOT_DIR/runtime-artifacts/observability}"
mkdir -p "$ARTIFACT_DIR"
OUT="$ARTIFACT_DIR/observability-gate.json"

for service in prometheus grafana loki tempo promtail alertmanager otel-collector blackbox-exporter aitec-worker; do
  if ! docker compose ps --status running --services | grep -qx "$service"; then
    echo "required observability/runtime service not running: $service" >&2
    echo "Start Compose with COMPOSE_PROFILES=full,ops and docker-compose.ci.yml + docker-compose.ops.yml" >&2
    exit 1
  fi
done

docker compose exec -T aitec-engine python - <<'PY' > "$OUT"
import json,time,urllib.parse,urllib.request

checks={
  'prometheus':'http://prometheus:9090/-/ready',
  'grafana':'http://grafana:3000/api/health',
  'loki':'http://loki:3100/ready',
  'tempo':'http://tempo:3200/ready',
  'promtail':'http://promtail:9080/ready',
  'alertmanager':'http://alertmanager:9093/-/ready',
  'otel-collector':'http://otel-collector:13133/',
  'blackbox-exporter':'http://blackbox-exporter:9115/-/healthy',
  'ai-gateway-metrics':'http://ai-gateway:3003/metrics',
  'aitec-worker-metrics':'http://aitec-worker:9104/metrics',
}

def get(url,timeout=5):
    req=urllib.request.Request(url,headers={'User-Agent':'lotediretor-observability-gate'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        body=r.read().decode('utf-8','replace')
        if not (200 <= r.status < 300):
            raise RuntimeError(f'{url}:HTTP {r.status}')
        return body

def prom_query(expr):
    query=urllib.parse.urlencode({'query':expr})
    raw=json.loads(get('http://prometheus:9090/api/v1/query?'+query))
    if raw.get('status')!='success':raise RuntimeError('prometheus_query_failed:'+expr)
    return raw.get('data',{}).get('result',[])

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
required={'platform-api','control-api','ai-gateway','solar-engine','aitec-engine','aitec-worker','blackbox-http'}
by_pool={}
for target in active:
    pool=target.get('scrapePool')
    if pool in required:
        by_pool.setdefault(pool,[]).append({
            'health':target.get('health'),
            'lastError':target.get('lastError') or '',
            'scrapeUrl':target.get('scrapeUrl'),
            'labels':target.get('labels') or {},
        })
missing=sorted(required-set(by_pool))
down=[]
for pool,items in by_pool.items():
    for item in items:
        if item['health']!='up' or item['lastError']:
            down.append(f'{pool}:{item["labels"].get("instance",item["scrapeUrl"])}')
if missing:raise RuntimeError('prometheus_targets_missing:'+','.join(missing))
if down:raise RuntimeError('prometheus_targets_down:'+','.join(sorted(down)))

probe_targets=[
  'http://ai-gateway:3003/ai/health',
  'http://gateway:8080/api/v1/health',
  'http://keycloak:8080/realms/lotediretor/.well-known/openid-configuration',
]
probe_results={}
for target in probe_targets:
    values=prom_query(f'probe_success{{instance="{target}"}}')
    value=float(values[0]['value'][1]) if values else 0.0
    probe_results[target]=value
    if value!=1.0:raise RuntimeError('blackbox_probe_failed:'+target)

ai_requests=prom_query('sum(lotediretor_http_requests_total{service="ai-gateway"})')
if not ai_requests or float(ai_requests[0]['value'][1])<=0:
    raise RuntimeError('ai_gateway_red_metrics_missing_or_empty')
ai_latency=prom_query('sum(lotediretor_http_request_duration_seconds_count{service="ai-gateway"})')
if not ai_latency or float(ai_latency[0]['value'][1])<=0:
    raise RuntimeError('ai_gateway_latency_histogram_missing_or_empty')

worker_ready=prom_query('lotediretor_aitec_worker_ready')
if not worker_ready or float(worker_ready[0]['value'][1])!=1.0:
    raise RuntimeError('aitec_worker_not_ready')
last_db=prom_query('lotediretor_aitec_worker_last_db_success_unixtime')
if not last_db:raise RuntimeError('aitec_worker_last_db_success_missing')
last_db_value=float(last_db[0]['value'][1])
last_db_age=max(0.0,time.time()-last_db_value)
if last_db_age>60:raise RuntimeError(f'aitec_worker_db_cycle_stale:{last_db_age:.1f}s')

queue_series=prom_query('lotediretor_aitec_jobs')
queue_by_status={item.get('metric',{}).get('status'):float(item['value'][1]) for item in queue_series}
required_states={'QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED'}
missing_states=sorted(required_states-set(queue_by_status))
if missing_states:raise RuntimeError('aitec_queue_metrics_missing_states:'+','.join(missing_states))
oldest_series=prom_query('lotediretor_aitec_oldest_job_age_seconds')
oldest_by_status={item.get('metric',{}).get('status'):float(item['value'][1]) for item in oldest_series}
if not required_states.issubset(oldest_by_status):
    raise RuntimeError('aitec_queue_age_metrics_incomplete')

rules=json.loads(get('http://prometheus:9090/api/v1/rules'))
rule_names=[]
for group in rules.get('data',{}).get('groups',[]):
    for rule in group.get('rules',[]):
        if rule.get('name'):rule_names.append(rule['name'])
required_rules={
  'LoteDiretorServiceDown','LoteDiretorTargetMissing','LoteDiretorEdgeProbeDown',
  'LoteDiretorHigh5xxRate','LoteDiretorCritical5xxRate','LoteDiretorHighP95Latency',
  'LoteDiretorAitecWorkerDown','LoteDiretorAitecWorkerDbStale','LoteDiretorAitecQueueBacklog',
  'LoteDiretorAitecQueueStalled','LoteDiretorAitecQueueCriticallyStalled',
  'LoteDiretorAitecJobFailures','LoteDiretorAitecRetryStorm'
}
missing_rules=sorted(required_rules-set(rule_names))
if missing_rules:raise RuntimeError('prometheus_rules_missing:'+','.join(missing_rules))

print(json.dumps({
  'status':'PASS',
  'components':results,
  'prometheusTargets':by_pool,
  'blackboxProbes':probe_results,
  'aiGateway':{
    'redRequests':float(ai_requests[0]['value'][1]),
    'latencyHistogramCount':float(ai_latency[0]['value'][1]),
  },
  'aitecWorker':{
    'ready':True,
    'lastDbSuccessUnix':last_db_value,
    'lastDbSuccessAgeSeconds':round(last_db_age,3),
    'jobsByStatus':queue_by_status,
    'oldestJobAgeSeconds':oldest_by_status,
  },
  'alertRules':sorted(set(rule_names)),
},sort_keys=True))
PY

cat "$OUT"
echo "Observability runtime gate PASS"
