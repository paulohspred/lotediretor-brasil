#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
env=os.environ.copy()
fixtures={
    'PUBLIC_DOMAIN':'app.example.com','AUTH_DOMAIN':'auth.example.com','ACME_EMAIL':'ops@example.com',
    'KEYCLOAK_ADMIN':'ld-admin','KEYCLOAK_ADMIN_PASSWORD':'prod-keycloak-fixture-DoNotUse-2026',
    'INTERNAL_API_TOKEN':'prod-internal-fixture-DoNotUse-2026','OIDC_CLIENT_SECRET':'prod-oidc-fixture-DoNotUse-2026',
    'PLATFORM_DB_MIGRATION_USER':'ld_platform_migration','PLATFORM_DB_MIGRATION_PASSWORD':'prod-platform-owner-fixture-2026',
    'PLATFORM_DB_NAME':'lotediretor','PLATFORM_DB_APP_USER':'ld_platform_app','PLATFORM_DB_APP_PASSWORD':'prod-platform-app-fixture-2026',
    'PLATFORM_DB_TILES_USER':'ld_tiles','PLATFORM_DB_TILES_PASSWORD':'prod-tiles-fixture-2026',
    'PLATFORM_DB_EVENT_PASSWORD':'prod-event-fixture-2026','PLATFORM_DB_WORKER_PASSWORD':'prod-worker-fixture-2026',
    'CONTROL_DB_MIGRATION_USER':'ld_control_migration','CONTROL_DB_MIGRATION_PASSWORD':'prod-control-owner-fixture-2026',
    'CONTROL_DB_NAME':'lotediretor_control','CONTROL_DB_APP_USER':'ld_control_app','CONTROL_DB_APP_PASSWORD':'prod-control-app-fixture-2026',
    'CONTROL_DB_WORKER_PASSWORD':'prod-control-worker-fixture-2026','S3_ACCESS_KEY':'ld-object','S3_SECRET_KEY':'prod-object-fixture-2026',
    'SESSION_COOKIE_SECURE':'true','ALLOW_LOCAL_AUTO_MEMBERSHIP':'false',
}
for k,v in fixtures.items(): env.setdefault(k,v)

cmd=['docker','compose','-f','docker-compose.yml','-f','docker-compose.production.yml','--profile','full','--profile','ops','config','--format','json']
try:
    raw=subprocess.check_output(cmd,cwd=ROOT,env=env,text=True,stderr=subprocess.STDOUT,timeout=60)
except subprocess.CalledProcessError as exc:
    print(exc.output,file=sys.stderr);raise SystemExit('production compose rendering failed')
except Exception as exc:
    raise SystemExit(f'production compose rendering failed: {exc}')
try: model=json.loads(raw)
except Exception as exc: raise SystemExit(f'production compose JSON invalid: {exc}')
services=model.get('services') or {}
errors=[]


def svc(name):
    x=services.get(name)
    if not isinstance(x,dict): errors.append(f'missing service:{name}');return {}
    return x


def envmap(name):
    e=svc(name).get('environment') or {}
    if isinstance(e,list):
        out={}
        for item in e:
            if '=' in str(item): k,v=str(item).split('=',1);out[k]=v
        return out
    return {str(k):'' if v is None else str(v) for k,v in e.items()}


def port_targets(name):
    out=[]
    for p in svc(name).get('ports') or []:
        if isinstance(p,dict): out.append((str(p.get('target')),str(p.get('published')),str(p.get('host_ip') or '')))
        else: out.append((str(p),str(p),''))
    return out


def positive_number(value, label):
    try:
        n=float(value)
    except (TypeError,ValueError):
        errors.append(f'{label} is not numeric:{value}')
        return None
    if n <= 0: errors.append(f'{label} must be > 0:{value}')
    return n


for name in services:
    ports=port_targets(name)
    if name=='gateway':
        targets={p[0] for p in ports}
        if not {'80','443'}.issubset(targets): errors.append(f'gateway missing 80/443:{ports}')
    elif ports:
        errors.append(f'internal service publishes host port:{name}:{ports}')

platform=envmap('platform-api');control=envmap('control-api');ai=envmap('ai-gateway')
solar=envmap('solar-engine');aitec=envmap('aitec-engine');aitec_worker=envmap('aitec-worker')
if platform.get('NODE_ENV')!='production': errors.append('platform-api NODE_ENV not production')
if control.get('NODE_ENV')!='production': errors.append('control-api NODE_ENV not production')
if ai.get('NODE_ENV')!='production': errors.append('ai-gateway NODE_ENV not production')
if solar.get('APP_ENV')!='production': errors.append('solar-engine APP_ENV not production')
if aitec.get('APP_ENV')!='production': errors.append('aitec-engine APP_ENV not production')
if platform.get('SESSION_COOKIE_SECURE')!='true': errors.append('platform secure cookie disabled')
if platform.get('ALLOW_LOCAL_AUTO_MEMBERSHIP')!='false': errors.append('platform local auto-membership enabled')
if platform.get('RUN_MIGRATIONS_ON_START')!='false': errors.append('platform runtime migrations enabled')
if control.get('RUN_MIGRATIONS_ON_START')!='false': errors.append('control runtime migrations enabled')
if platform.get('PLATFORM_MIGRATION_DATABASE_URL','')!='': errors.append('platform-api carries migration-owner DSN')
if control.get('CONTROL_MIGRATION_DATABASE_URL','')!='': errors.append('control-api carries migration-owner DSN')
if 'ld_platform_app:' not in platform.get('PLATFORM_DATABASE_URL',''): errors.append('platform-api does not use app DB role')
if 'ld_control_app:' not in control.get('CONTROL_DATABASE_URL',''): errors.append('control-api does not use app DB role')

otel_expected='http://otel-collector:4318'
for name,service_env in (
    ('platform-api',platform),('control-api',control),('ai-gateway',ai),
    ('solar-engine',solar),('aitec-engine',aitec),
):
    endpoint=service_env.get('OTEL_EXPORTER_OTLP_ENDPOINT','').rstrip('/')
    if endpoint!=otel_expected:
        errors.append(f'{name} OTLP endpoint not production collector:{endpoint or "missing"}')

if 'ld_platform_migration:' not in envmap('platform-migrate').get('PLATFORM_MIGRATION_DATABASE_URL',''): errors.append('platform-migrate missing migration role')
if 'ld_control_migration:' not in envmap('control-migrate').get('CONTROL_MIGRATION_DATABASE_URL',''): errors.append('control-migrate missing migration role')

keycloak=svc('keycloak');command=[str(x) for x in keycloak.get('command') or []]
if 'start-dev' in command or 'start' not in command: errors.append(f'keycloak production command unsafe:{command}')
kenv=envmap('keycloak')
if kenv.get('KC_HOSTNAME_STRICT')!='true': errors.append('keycloak hostname strict disabled')
if kenv.get('KC_HEALTH_ENABLED')!='true' or kenv.get('KC_METRICS_ENABLED')!='true': errors.append('keycloak health/metrics disabled')

if port_targets('opensearch'): errors.append('opensearch exposed on host')

worker_expectations={
 'geo-worker':('PLATFORM_DATABASE_URL','lotediretor_worker:'),
 'document-worker':('PLATFORM_DATABASE_URL','lotediretor_worker:'),
 'report-worker':('PLATFORM_DATABASE_URL','lotediretor_worker:'),
 'aitec-worker':('PLATFORM_DATABASE_URL','lotediretor_worker:'),
 'data-pipelines':('PLATFORM_DATABASE_URL','lotediretor_worker:'),
 'ai-ingest':('PLATFORM_DATABASE_URL','lotediretor_worker:'),
 'event-dispatcher':('PLATFORM_EVENT_DATABASE_URL','lotediretor_event_dispatcher:'),
 'billing-worker':('CONTROL_DATABASE_URL','lotediretor_control_worker:'),
}
for name,(key,needle) in worker_expectations.items():
    if needle not in envmap(name).get(key,''): errors.append(f'{name} does not use least-privilege role in {key}')

worker=svc('aitec-worker')
if aitec_worker.get('AITEC_METRICS_PORT')!='9104': errors.append('aitec-worker metrics port must be 9104')
retry_base=positive_number(aitec_worker.get('AITEC_JOB_RETRY_BASE_SECONDS'),'aitec-worker retry base')
retry_max=positive_number(aitec_worker.get('AITEC_JOB_RETRY_MAX_SECONDS'),'aitec-worker retry max')
if retry_base is not None and retry_max is not None and retry_max < retry_base:
    errors.append('aitec-worker retry max is lower than retry base')
if worker.get('restart') not in ('unless-stopped','always'):
    errors.append(f'aitec-worker restart policy not resilient:{worker.get("restart") or "missing"}')
depends=worker.get('depends_on') or {}
aitec_dep=depends.get('aitec-engine') if isinstance(depends,dict) else None
condition=aitec_dep.get('condition') if isinstance(aitec_dep,dict) else None
if condition!='service_healthy': errors.append(f'aitec-worker does not wait for healthy aitec-engine:{condition}')
healthcheck=worker.get('healthcheck') or {}
health_text=json.dumps(healthcheck,sort_keys=True)
if '9104/metrics' not in health_text: errors.append('aitec-worker healthcheck does not probe metrics endpoint')

serialized=json.dumps(model,sort_keys=True)
for marker in ['change-me','lotediretor_local','local-lotediretor-secret','local-internal-change-me']:
    if marker in serialized: errors.append(f'development marker leaked into production model:{marker}')

report={
    'status':'PASS' if not errors else 'FAIL',
    'services':len(services),
    'publishedPorts':{n:port_targets(n) for n in services if port_targets(n)},
    'telemetry':{name:envmap(name).get('OTEL_EXPORTER_OTLP_ENDPOINT') for name in ('platform-api','control-api','ai-gateway','solar-engine','aitec-engine')},
    'aitecWorker':{
        'databaseRoleOk':'lotediretor_worker:' in aitec_worker.get('PLATFORM_DATABASE_URL',''),
        'metricsPort':aitec_worker.get('AITEC_METRICS_PORT'),
        'retryBaseSeconds':aitec_worker.get('AITEC_JOB_RETRY_BASE_SECONDS'),
        'retryMaxSeconds':aitec_worker.get('AITEC_JOB_RETRY_MAX_SECONDS'),
        'restart':worker.get('restart'),
        'engineDependencyCondition':condition,
    },
    'errors':errors,
}
print(json.dumps(report,indent=2,ensure_ascii=False))
if errors: raise SystemExit(1)
