#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DIGEST='a'*64
fixture_env={
 'PUBLIC_DOMAIN':'app.example.com','AUTH_DOMAIN':'auth.example.com','ACME_EMAIL':'ops@example.com',
 'KEYCLOAK_ADMIN':'release-ci','KEYCLOAK_ADMIN_PASSWORD':'release-keycloak-fixture-2026',
 'INTERNAL_API_TOKEN':'release-internal-fixture-2026','OIDC_CLIENT_SECRET':'release-oidc-fixture-2026',
 'PLATFORM_DB_MIGRATION_USER':'ld_platform_migration','PLATFORM_DB_MIGRATION_PASSWORD':'release-platform-owner-2026',
 'PLATFORM_DB_NAME':'lotediretor','PLATFORM_DB_APP_USER':'ld_platform_app','PLATFORM_DB_APP_PASSWORD':'release-platform-app-2026',
 'PLATFORM_DB_TILES_USER':'ld_tiles','PLATFORM_DB_TILES_PASSWORD':'release-tiles-2026',
 'PLATFORM_DB_EVENT_PASSWORD':'release-event-2026','PLATFORM_DB_WORKER_PASSWORD':'release-worker-2026',
 'CONTROL_DB_MIGRATION_USER':'ld_control_migration','CONTROL_DB_MIGRATION_PASSWORD':'release-control-owner-2026',
 'CONTROL_DB_NAME':'lotediretor_control','CONTROL_DB_APP_USER':'ld_control_app','CONTROL_DB_APP_PASSWORD':'release-control-app-2026',
 'CONTROL_DB_WORKER_PASSWORD':'release-control-worker-2026','S3_ACCESS_KEY':'ld-object','S3_SECRET_KEY':'release-object-2026',
}
image_vars={
 'PLATFORM_API_IMAGE':'ghcr.io/lotediretor/platform-api',
 'CONTROL_API_IMAGE':'ghcr.io/lotediretor/control-api',
 'AI_GATEWAY_IMAGE':'ghcr.io/lotediretor/ai-gateway',
 'SOLAR_ENGINE_IMAGE':'ghcr.io/lotediretor/solar-engine',
 'AITEC_ENGINE_IMAGE':'ghcr.io/lotediretor/aitec-engine',
 'AITEC_WORKER_IMAGE':'ghcr.io/lotediretor/aitec-worker',
 'EVENT_DISPATCHER_IMAGE':'ghcr.io/lotediretor/event-dispatcher',
 'GEO_WORKER_IMAGE':'ghcr.io/lotediretor/geo-worker',
 'DOCUMENT_WORKER_IMAGE':'ghcr.io/lotediretor/document-worker',
 'REPORT_WORKER_IMAGE':'ghcr.io/lotediretor/report-worker',
 'RURAL_MONITOR_WORKER_IMAGE':'ghcr.io/lotediretor/rural-monitor-worker',
 'RURAL_EXPORT_WORKER_IMAGE':'ghcr.io/lotediretor/rural-export-worker',
 'BILLING_WORKER_IMAGE':'ghcr.io/lotediretor/billing-worker',
 'DATA_PIPELINES_IMAGE':'ghcr.io/lotediretor/data-pipelines',
 'AI_INGEST_IMAGE':'ghcr.io/lotediretor/ai-ingest',
 'SITE_WEB_IMAGE':'ghcr.io/lotediretor/site-web',
 'CLIENT_WEB_IMAGE':'ghcr.io/lotediretor/client-web',
 'ADMIN_WEB_IMAGE':'ghcr.io/lotediretor/admin-web',
}
env=os.environ.copy()
for k,v in fixture_env.items(): env.setdefault(k,v)
for k,repo in image_vars.items(): env.setdefault(k,f'{repo}@sha256:{DIGEST}')
cmd=['docker','compose','-f','docker-compose.yml','-f','docker-compose.production.yml','-f','docker-compose.release.yml','--profile','full','--profile','ops','config','--format','json']
try:
 raw=subprocess.check_output(cmd,cwd=ROOT,env=env,text=True,stderr=subprocess.STDOUT,timeout=60)
except subprocess.CalledProcessError as exc:
 print(exc.output,file=sys.stderr);raise SystemExit('immutable release render failed')
model=json.loads(raw);services=model.get('services') or {}
expected={
 'platform-api','platform-migrate','control-api','control-migrate','ai-gateway','solar-engine','aitec-engine','aitec-worker',
 'event-dispatcher','geo-worker','document-worker','report-worker','rural-monitor-worker','rural-export-worker',
 'billing-worker','data-pipelines','ai-ingest','site-web','client-web','admin-web'
}
errors=[]
pattern=re.compile(r'^.+@sha256:[0-9a-fA-F]{64}$')
for name in sorted(expected):
 svc=services.get(name)
 if not isinstance(svc,dict): errors.append(f'missing promoted service:{name}');continue
 if svc.get('build') not in (None,{}): errors.append(f'{name} still contains build configuration')
 image=str(svc.get('image') or '')
 if not pattern.match(image): errors.append(f'{name} image is not immutable digest:{image!r}')
if services.get('platform-api',{}).get('image')!=services.get('platform-migrate',{}).get('image'):
 errors.append('platform migration artifact differs from platform-api artifact')
if services.get('control-api',{}).get('image')!=services.get('control-migrate',{}).get('image'):
 errors.append('control migration artifact differs from control-api artifact')
report={'status':'PASS' if not errors else 'FAIL','promotedServices':len(expected),'errors':errors,'images':{n:services.get(n,{}).get('image') for n in sorted(expected)}}
print(json.dumps(report,indent=2))
if errors: raise SystemExit(1)
