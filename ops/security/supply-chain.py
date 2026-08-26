#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(os.environ.get('SECURITY_ARTIFACT_DIR',ROOT/'runtime-artifacts/security')).resolve()
OUT.mkdir(parents=True,exist_ok=True)

OWN_IMAGE_VARS={
 'platform-api':'PLATFORM_API_IMAGE','platform-migrate':'PLATFORM_API_IMAGE',
 'control-api':'CONTROL_API_IMAGE','control-migrate':'CONTROL_API_IMAGE',
 'ai-gateway':'AI_GATEWAY_IMAGE','solar-engine':'SOLAR_ENGINE_IMAGE','aitec-engine':'AITEC_ENGINE_IMAGE','aitec-worker':'AITEC_WORKER_IMAGE',
 'event-dispatcher':'EVENT_DISPATCHER_IMAGE','geo-worker':'GEO_WORKER_IMAGE','document-worker':'DOCUMENT_WORKER_IMAGE','report-worker':'REPORT_WORKER_IMAGE',
 'rural-monitor-worker':'RURAL_MONITOR_WORKER_IMAGE','rural-export-worker':'RURAL_EXPORT_WORKER_IMAGE','billing-worker':'BILLING_WORKER_IMAGE',
 'data-pipelines':'DATA_PIPELINES_IMAGE','ai-ingest':'AI_INGEST_IMAGE','site-web':'SITE_WEB_IMAGE','client-web':'CLIENT_WEB_IMAGE','admin-web':'ADMIN_WEB_IMAGE',
}

fixtures={
 'PUBLIC_DOMAIN':'supply.example.com','AUTH_DOMAIN':'auth-supply.example.com','ACME_EMAIL':'supply@example.com',
 'KEYCLOAK_ADMIN':'supply-admin','KEYCLOAK_ADMIN_PASSWORD':'supply-keycloak-fixture-2026',
 'INTERNAL_API_TOKEN':'supply-internal-fixture-2026','OIDC_CLIENT_SECRET':'supply-oidc-fixture-2026',
 'PLATFORM_DB_MIGRATION_USER':'ld_platform_migration','PLATFORM_DB_MIGRATION_PASSWORD':'supply-platform-owner-2026',
 'PLATFORM_DB_NAME':'lotediretor','PLATFORM_DB_APP_USER':'ld_platform_app','PLATFORM_DB_APP_PASSWORD':'supply-platform-app-2026',
 'PLATFORM_DB_TILES_USER':'ld_tiles','PLATFORM_DB_TILES_PASSWORD':'supply-tiles-2026',
 'PLATFORM_DB_EVENT_PASSWORD':'supply-event-2026','PLATFORM_DB_WORKER_PASSWORD':'supply-worker-2026',
 'CONTROL_DB_MIGRATION_USER':'ld_control_migration','CONTROL_DB_MIGRATION_PASSWORD':'supply-control-owner-2026',
 'CONTROL_DB_NAME':'lotediretor_control','CONTROL_DB_APP_USER':'ld_control_app','CONTROL_DB_APP_PASSWORD':'supply-control-app-2026',
 'CONTROL_DB_WORKER_PASSWORD':'supply-control-worker-2026','S3_ACCESS_KEY':'supply-object','S3_SECRET_KEY':'supply-object-secret-2026',
 'SESSION_COOKIE_SECURE':'true','ALLOW_LOCAL_AUTO_MEMBERSHIP':'false',
 'MINIO_IMAGE':'minio/minio:RELEASE.2025-07-23T15-54-02Z',
 'MINIO_MC_IMAGE':'minio/mc:RELEASE.2025-08-13T08-35-41Z',
}
env=os.environ.copy()
for k,v in fixtures.items(): env.setdefault(k,v)
for var in sorted(set(OWN_IMAGE_VARS.values())):
    digest=hashlib.sha256(('lotediretor:'+var).encode()).hexdigest()
    repo=var.lower().removesuffix('_image').replace('_','-')
    env.setdefault(var,f'ghcr.io/lotediretor/{repo}@sha256:{digest}')

cmd=['docker','compose','-f','docker-compose.yml','-f','docker-compose.production.yml','-f','docker-compose.release.yml','--profile','full','--profile','ops','config','--format','json']
try:
    raw=subprocess.check_output(cmd,cwd=ROOT,env=env,text=True,stderr=subprocess.STDOUT,timeout=90)
except subprocess.CalledProcessError as exc:
    print(exc.output,file=sys.stderr);raise SystemExit('supply-chain production candidate render failed')
except Exception as exc:
    raise SystemExit(f'supply-chain production candidate render failed:{exc}')
model=json.loads(raw);services=model.get('services') or {}
errors=[];warnings=[]

floating_tags={'latest','edge','nightly','main','master','develop','dev','snapshot','canary'}
def image_ref_state(image:str):
    image=image.strip()
    if not image:return 'missing'
    if '@sha256:' in image:
        digest=image.rsplit('@sha256:',1)[1]
        return 'digest' if re.fullmatch(r'[0-9a-fA-F]{64}',digest or '') else 'invalid_digest'
    leaf=image.rsplit('/',1)[-1]
    if ':' not in leaf:return 'floating_untagged'
    tag=leaf.rsplit(':',1)[1].lower()
    if tag in floating_tags:return 'floating_tag'
    return 'tag'

compose_components=[]
for name in sorted(services):
    service=services[name] or {}
    image=str(service.get('image') or '')
    if not image: continue
    state=image_ref_state(image)
    owned=name in OWN_IMAGE_VARS
    if state.startswith('floating') or state in {'missing','invalid_digest'}:
        errors.append(f'{name} has non-reproducible image reference:{image}:{state}')
    if owned and state!='digest': errors.append(f'owned release artifact is not digest pinned:{name}:{image}')
    if not owned and state=='tag': warnings.append(f'third-party image uses a pinned tag rather than digest:{name}:{image}')
    if image.startswith(('cloudpirates/','coollabsio/','derklaro/','sourcemation/')) and 'minio' in image.lower():
        errors.append(f'unapproved MinIO mirror detected:{name}:{image}')
    compose_components.append({'service':name,'image':image,'referenceState':state,'owned':owned})

# The project intentionally uses official archived MinIO images as local/portable
# object-storage fixtures until a final production provider is selected.
for service,expected_prefix in [('minio','minio/minio:RELEASE.'),('minio-init','minio/mc:RELEASE.')]:
    image=str((services.get(service) or {}).get('image') or '')
    if not image.startswith(expected_prefix): errors.append(f'{service} must use an explicit official MinIO release tag:{image}')

components=[]
seen=set()
def add_component(kind,name,version=None,purl=None,properties=None):
    key=(kind,name,version or '',purl or '')
    if key in seen:return
    seen.add(key)
    item={'type':kind,'name':name}
    if version:item['version']=version
    if purl:item['purl']=purl
    if properties:item['properties']=[{'name':str(k),'value':str(v)} for k,v in sorted(properties.items())]
    components.append(item)

# npm dependency inventory from the committed lockfile; transitive packages are
# included. Exact versions come from package-lock, not package.json ranges.
lock_path=ROOT/'package-lock.json'
if not lock_path.exists(): errors.append('package-lock.json missing')
else:
    try: lock=json.loads(lock_path.read_text(encoding='utf-8'))
    except Exception as exc: errors.append(f'package-lock.json invalid:{exc}');lock={}
    for path,meta in sorted((lock.get('packages') or {}).items()):
        if not path or not isinstance(meta,dict):continue
        version=str(meta.get('version') or '').strip()
        name=str(meta.get('name') or '').strip()
        if not name and 'node_modules/' in path:name=path.rsplit('node_modules/',1)[-1]
        if not name:continue
        purl=f'pkg:npm/{name.replace("@","%40",1) if name.startswith("@") else name}'
        if version:purl+=f'@{version}'
        add_component('library',name,version or None,purl,{'ecosystem':'npm','lockPath':path})

# Python dependencies: exact == pins are represented as versions; other
# constraints remain visible as properties rather than being silently resolved.
req_files=[]
for p in sorted(ROOT.rglob('requirements*.txt')):
    if any(part in {'.git','node_modules','runtime-artifacts','.venv','venv'} for part in p.parts):continue
    req_files.append(p)
    for raw_line in p.read_text(encoding='utf-8',errors='replace').splitlines():
        line=raw_line.strip()
        if not line or line.startswith(('#','-')):continue
        line=line.split(' #',1)[0].strip()
        m=re.match(r'^([A-Za-z0-9_.-]+)(?:\[([^\]]+)\])?\s*(==|~=|>=|<=|>|<)?\s*([^;\s]+)?',line)
        if not m:continue
        name,extras,op,value=m.group(1),m.group(2),m.group(3),m.group(4)
        version=value if op=='==' and value else None
        purl=f'pkg:pypi/{name.lower().replace("_","-")}' + (f'@{version}' if version else '')
        props={'ecosystem':'pypi','source':str(p.relative_to(ROOT)),'constraint':line}
        if extras:props['extras']=extras
        add_component('library',name,version,purl,props)

# Base images are part of the source supply chain even when an application image
# is later promoted by digest.
dockerfiles=[]
for p in sorted(ROOT.rglob('Dockerfile')):
    if any(part in {'.git','node_modules','runtime-artifacts'} for part in p.parts):continue
    dockerfiles.append(p)
    for line in p.read_text(encoding='utf-8',errors='replace').splitlines():
        m=re.match(r'^\s*FROM\s+(?:--platform=\S+\s+)?([^\s]+)',line,re.I)
        if not m:continue
        image=m.group(1)
        state=image_ref_state(image) if '$' not in image else 'build_arg'
        add_component('container',image,None,None,{'source':str(p.relative_to(ROOT)),'referenceState':state})
        if state.startswith('floating'): errors.append(f'floating Dockerfile base image:{p.relative_to(ROOT)}:{image}')

for item in compose_components:
    add_component('container',item['image'],None,None,{'composeService':item['service'],'referenceState':item['referenceState'],'owned':str(item['owned']).lower()})

components.sort(key=lambda x:(x.get('type',''),x.get('name',''),x.get('version',''),x.get('purl','')))
fingerprint=hashlib.sha256(json.dumps(components,sort_keys=True,separators=(',',':')).encode()).hexdigest()
serial=str(uuid.uuid5(uuid.NAMESPACE_URL,'urn:lotediretor:sbom:'+fingerprint))
commit=None
try: commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL,timeout=5).strip()
except Exception: pass

sbom={
 'bomFormat':'CycloneDX','specVersion':'1.5','serialNumber':f'urn:uuid:{serial}','version':1,
 'metadata':{
   'timestamp':datetime.now(timezone.utc).isoformat(),
   'component':{'type':'application','name':'lotediretor-brasil','version':commit or 'unknown'},
   'properties':[{'name':'lotediretor:componentFingerprintSha256','value':fingerprint}],
 },
 'components':components,
}
(OUT/'sbom.cdx.json').write_text(json.dumps(sbom,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

report={
 'status':'PASS' if not errors else 'FAIL',
 'classification':'LOCAL_SUPPLY_CHAIN_INVENTORY_NOT_VULNERABILITY_SCAN',
 'commit':commit,
 'componentFingerprintSha256':fingerprint,
 'components':len(components),
 'npmComponents':sum(1 for c in components if any(p.get('value')=='npm' for p in c.get('properties',[]) if p.get('name')=='ecosystem')),
 'pythonRequirementFiles':[str(p.relative_to(ROOT)) for p in req_files],
 'dockerfiles':[str(p.relative_to(ROOT)) for p in dockerfiles],
 'composeImages':compose_components,
 'errors':errors,
 'warnings':sorted(set(warnings)),
 'sbom':'sbom.cdx.json',
 'note':'This inventory validates committed dependency/image references and emits CycloneDX. It does not replace CVE scanning, image signature verification, provenance attestations or an independent pentest.',
}
(OUT/'supply-chain.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2,ensure_ascii=False))
if errors: raise SystemExit(1)
