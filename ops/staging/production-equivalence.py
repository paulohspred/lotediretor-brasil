#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
OWN_IMAGES={
 'platform-api':'PLATFORM_API_IMAGE','platform-migrate':'PLATFORM_API_IMAGE',
 'control-api':'CONTROL_API_IMAGE','control-migrate':'CONTROL_API_IMAGE',
 'ai-gateway':'AI_GATEWAY_IMAGE','solar-engine':'SOLAR_ENGINE_IMAGE','aitec-engine':'AITEC_ENGINE_IMAGE','aitec-worker':'AITEC_WORKER_IMAGE',
 'event-dispatcher':'EVENT_DISPATCHER_IMAGE','geo-worker':'GEO_WORKER_IMAGE','document-worker':'DOCUMENT_WORKER_IMAGE','report-worker':'REPORT_WORKER_IMAGE',
 'rural-monitor-worker':'RURAL_MONITOR_WORKER_IMAGE','rural-export-worker':'RURAL_EXPORT_WORKER_IMAGE','billing-worker':'BILLING_WORKER_IMAGE',
 'data-pipelines':'DATA_PIPELINES_IMAGE','ai-ingest':'AI_INGEST_IMAGE','site-web':'SITE_WEB_IMAGE','client-web':'CLIENT_WEB_IMAGE','admin-web':'ADMIN_WEB_IMAGE',
}

env=os.environ.copy()
fixtures={
 'PUBLIC_DOMAIN':'staging.example.com','AUTH_DOMAIN':'auth-staging.example.com','ACME_EMAIL':'staging@example.com',
 'KEYCLOAK_ADMIN':'staging-admin','KEYCLOAK_ADMIN_PASSWORD':'staging-keycloak-fixture-2026',
 'INTERNAL_API_TOKEN':'staging-internal-fixture-2026','OIDC_CLIENT_SECRET':'staging-oidc-fixture-2026',
 'PLATFORM_DB_MIGRATION_USER':'ld_platform_migration','PLATFORM_DB_MIGRATION_PASSWORD':'staging-platform-owner-2026',
 'PLATFORM_DB_NAME':'lotediretor','PLATFORM_DB_APP_USER':'ld_platform_app','PLATFORM_DB_APP_PASSWORD':'staging-platform-app-2026',
 'PLATFORM_DB_TILES_USER':'ld_tiles','PLATFORM_DB_TILES_PASSWORD':'staging-tiles-2026',
 'PLATFORM_DB_EVENT_PASSWORD':'staging-event-2026','PLATFORM_DB_WORKER_PASSWORD':'staging-worker-2026',
 'CONTROL_DB_MIGRATION_USER':'ld_control_migration','CONTROL_DB_MIGRATION_PASSWORD':'staging-control-owner-2026',
 'CONTROL_DB_NAME':'lotediretor_control','CONTROL_DB_APP_USER':'ld_control_app','CONTROL_DB_APP_PASSWORD':'staging-control-app-2026',
 'CONTROL_DB_WORKER_PASSWORD':'staging-control-worker-2026','S3_ACCESS_KEY':'staging-object','S3_SECRET_KEY':'staging-object-secret-2026',
 'SESSION_COOKIE_SECURE':'true','ALLOW_LOCAL_AUTO_MEMBERSHIP':'false',
}
for k,v in fixtures.items(): env.setdefault(k,v)

for var in sorted(set(OWN_IMAGES.values())):
    digest=hashlib.sha256(var.encode()).hexdigest()
    env.setdefault(var,f'ghcr.io/lotediretor/{var.lower().replace("_image","").replace("_","-")}@sha256:{digest}')


def render(files:list[str]):
    cmd=['docker','compose']
    for f in files: cmd += ['-f',f]
    cmd += ['--profile','full','--profile','ops','config','--format','json']
    try:
        raw=subprocess.check_output(cmd,cwd=ROOT,env=env,text=True,stderr=subprocess.STDOUT,timeout=90)
    except subprocess.CalledProcessError as exc:
        print(exc.output,file=sys.stderr);raise SystemExit(f'compose render failed:{files}')
    return json.loads(raw)

production=render(['docker-compose.yml','docker-compose.production.yml'])
candidate=render(['docker-compose.yml','docker-compose.production.yml','docker-compose.release.yml'])
prod_services=production.get('services') or {}
cand_services=candidate.get('services') or {}
errors=[]

if set(prod_services)!=set(cand_services):
    errors.append(f'service topology differs: production_only={sorted(set(prod_services)-set(cand_services))} candidate_only={sorted(set(cand_services)-set(prod_services))}')

immutable_re=re.compile(r'^.+@sha256:[0-9a-f]{64}$')
for service,var in OWN_IMAGES.items():
    item=cand_services.get(service) or {}
    image=str(item.get('image') or '')
    if item.get('build') not in (None,{}): errors.append(f'{service} candidate still contains build configuration')
    if not immutable_re.match(image): errors.append(f'{service} image is not immutable sha256:{image}')
    expected=env[var]
    if image!=expected: errors.append(f'{service} image does not match promoted variable {var}')

if (cand_services.get('platform-migrate') or {}).get('image') != (cand_services.get('platform-api') or {}).get('image'):
    errors.append('platform migration image differs from platform-api image')
if (cand_services.get('control-migrate') or {}).get('image') != (cand_services.get('control-api') or {}).get('image'):
    errors.append('control migration image differs from control-api image')

# Release overlay may replace only build/image. Runtime topology, security,
# environment, dependencies, healthchecks, ports and volumes must remain equivalent.
def normalized_runtime(service:dict):
    return {k:v for k,v in service.items() if k not in {'build','image','pull_policy'}}

for name in sorted(set(prod_services)&set(cand_services)):
    p=normalized_runtime(prod_services[name])
    c=normalized_runtime(cand_services[name])
    if p!=c:
        errors.append(f'runtime contract differs for {name}')

# Explicit security/ops invariants are repeated here so a future normalization
# change cannot accidentally weaken the candidate while still comparing equal.
def envmap(service):
    e=(cand_services.get(service) or {}).get('environment') or {}
    if isinstance(e,list):
        out={}
        for x in e:
            if '=' in str(x): k,v=str(x).split('=',1);out[k]=v
        return out
    return {str(k):'' if v is None else str(v) for k,v in e.items()}

for service in ('platform-api','control-api','ai-gateway'):
    if envmap(service).get('NODE_ENV')!='production': errors.append(f'{service} not production mode')
for service in ('solar-engine','aitec-engine'):
    if envmap(service).get('APP_ENV')!='production': errors.append(f'{service} not production mode')
if envmap('platform-api').get('SESSION_COOKIE_SECURE')!='true': errors.append('candidate secure session cookie disabled')
if envmap('platform-api').get('ALLOW_LOCAL_AUTO_MEMBERSHIP')!='false': errors.append('candidate local auto membership enabled')
for service in ('platform-api','control-api'):
    if envmap(service).get('RUN_MIGRATIONS_ON_START')!='false': errors.append(f'{service} runtime migrations enabled')
for service in ('platform-api','control-api','ai-gateway','solar-engine','aitec-engine'):
    if envmap(service).get('OTEL_EXPORTER_OTLP_ENDPOINT','').rstrip('/')!='http://otel-collector:4318': errors.append(f'{service} not wired to OTLP collector')
if 'lotediretor_worker:' not in envmap('aitec-worker').get('PLATFORM_DATABASE_URL',''): errors.append('aitec-worker not using worker DB role')

report={
 'status':'PASS' if not errors else 'FAIL',
 'classification':'STRUCTURAL_STAGING_PARITY_CONTRACT_NOT_DEPLOYED_STAGING_EVIDENCE',
 'productionServices':len(prod_services),
 'candidateServices':len(cand_services),
 'immutableApplicationArtifacts':len(OWN_IMAGES),
 'errors':errors,
 'note':'This proves the release candidate preserves the rendered production runtime contract. It does not prove cloud/network/provider parity or production homologation.',
}
print(json.dumps(report,indent=2,ensure_ascii=False))
if errors: raise SystemExit(1)
