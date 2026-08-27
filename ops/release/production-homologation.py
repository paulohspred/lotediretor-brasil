#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SCHEMA='lotediretor-production-homologation-v1'
REQUIRED_GATES=(
    'independent_pentest',
    'provider_specific_ai_redteam',
    'production_like_staging',
    'release_image_signature_provenance',
    'live_canary_rollback',
    'production_ha_dr',
    'official_sources_and_providers',
    'professional_institutional_review',
    'main_branch_protection',
)
IMAGE_VARS=(
    'PLATFORM_API_IMAGE','CONTROL_API_IMAGE','AI_GATEWAY_IMAGE','SOLAR_ENGINE_IMAGE','AITEC_ENGINE_IMAGE','AITEC_WORKER_IMAGE',
    'EVENT_DISPATCHER_IMAGE','GEO_WORKER_IMAGE','DOCUMENT_WORKER_IMAGE','REPORT_WORKER_IMAGE','RURAL_MONITOR_WORKER_IMAGE',
    'RURAL_EXPORT_WORKER_IMAGE','BILLING_WORKER_IMAGE','DATA_PIPELINES_IMAGE','AI_INGEST_IMAGE','SITE_WEB_IMAGE','CLIENT_WEB_IMAGE','ADMIN_WEB_IMAGE',
)
DIGEST_RE=re.compile(r'^\S+@sha256:[0-9a-fA-F]{64}$')
COMMIT_RE=re.compile(r'^[0-9a-f]{40}$')


def iso_utc(value:str)->bool:
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        return dt.tzinfo is not None and dt <= datetime.now(timezone.utc)
    except Exception:
        return False


def validate(data:dict, *, enforce_environment:bool=True)->list[str]:
    errors=[]
    if data.get('schemaVersion')!=SCHEMA: errors.append('schemaVersion mismatch')
    if enforce_environment and data.get('environment')!='production': errors.append('environment must be production')
    if data.get('productionHomologated') is not True: errors.append('productionHomologated must be true')
    commit=str(data.get('candidateCommit') or '')
    if not COMMIT_RE.fullmatch(commit): errors.append('candidateCommit must be 40 lowercase hex chars')

    images=data.get('releaseImages')
    if not isinstance(images,list) or len(images)<18:
        errors.append('releaseImages must contain at least 18 immutable application artifacts')
    else:
        refs=[]
        for item in images:
            if not isinstance(item,dict): errors.append('releaseImages entries must be objects');continue
            name=str(item.get('name') or '').strip();ref=str(item.get('ref') or '').strip()
            if not name: errors.append('release image missing name')
            if not DIGEST_RE.fullmatch(ref): errors.append(f'release image is not immutable digest:{name}:{ref}')
            refs.append(ref)
        if len(set(refs))<16: errors.append('releaseImages contains implausibly few distinct immutable artifacts')

    gates=data.get('gates')
    if not isinstance(gates,dict):
        errors.append('gates must be an object');gates={}
    for name in REQUIRED_GATES:
        gate=gates.get(name)
        if not isinstance(gate,dict): errors.append(f'missing gate:{name}');continue
        if gate.get('status')!='PASS': errors.append(f'gate not PASS:{name}')
        evidence=str(gate.get('evidenceRef') or '').strip()
        owner=str(gate.get('owner') or '').strip()
        completed=str(gate.get('completedAtUtc') or '').strip()
        if not evidence: errors.append(f'gate missing evidenceRef:{name}')
        if not owner: errors.append(f'gate missing owner:{name}')
        if not iso_utc(completed): errors.append(f'gate invalid completedAtUtc:{name}')
        classification=str(gate.get('classification') or '').upper()
        if any(marker in classification for marker in ('LOCAL_SYNTHETIC','NOT_HOMOLOGATED','FIXTURE')):
            errors.append(f'gate uses non-production evidence classification:{name}')

    approved=data.get('approval')
    if not isinstance(approved,dict):
        errors.append('approval must be an object')
    else:
        if str(approved.get('approvedBy') or '').strip()=='': errors.append('approval.approvedBy is required')
        if str(approved.get('changeTicket') or '').strip()=='': errors.append('approval.changeTicket is required')
        if not iso_utc(str(approved.get('approvedAtUtc') or '')): errors.append('approval.approvedAtUtc invalid')

    return errors


def current_commit()->str|None:
    explicit=os.getenv('RELEASE_COMMIT_SHA','').strip().lower()
    if explicit: return explicit
    try:
        return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL,timeout=10).strip().lower()
    except Exception:
        return None


def self_test()->None:
    now=datetime.now(timezone.utc).isoformat()
    images=[{'name':name,'ref':f'ghcr.io/example/{name.lower().replace("_","-")}@sha256:{i:064x}'} for i,name in enumerate(IMAGE_VARS,1)]
    gates={name:{'status':'PASS','evidenceRef':f'evidence://{name}','owner':'test-owner','completedAtUtc':now,'classification':'PRODUCTION_EVIDENCE'} for name in REQUIRED_GATES}
    good={'schemaVersion':SCHEMA,'environment':'production','productionHomologated':True,'candidateCommit':'a'*40,'releaseImages':images,'gates':gates,'approval':{'approvedBy':'release-manager','approvedAtUtc':now,'changeTicket':'CHG-TEST'}}
    assert not validate(good), validate(good)
    bad=json.loads(json.dumps(good));bad['gates']['independent_pentest']['status']='PENDING'
    assert any('independent_pentest' in x for x in validate(bad))
    bad2=json.loads(json.dumps(good));bad2['gates']['production_ha_dr']['classification']='LOCAL_SYNTHETIC_DR_EVIDENCE_NOT_PRODUCTION_HOMOLOGATION'
    assert any('non-production evidence' in x for x in validate(bad2))
    print('Production homologation evidence schema/fail-closed self-test PASS')


if '--self-test' in sys.argv:
    self_test();raise SystemExit(0)

path=Path(os.environ.get('PRODUCTION_HOMOLOGATION_EVIDENCE','runtime-artifacts/release/production-homologation.json'))
if not path.is_absolute(): path=ROOT/path
if not path.is_file(): raise SystemExit(f'production homologation evidence file missing:{path}')
try: data=json.loads(path.read_text(encoding='utf-8'))
except Exception as exc: raise SystemExit(f'production homologation evidence invalid JSON:{exc}')
errors=validate(data)

commit=current_commit()
if commit and data.get('candidateCommit')!=commit:
    errors.append(f'candidateCommit does not match release commit:{data.get("candidateCommit")}!={commit}')

# If actual release image environment variables are present, evidence must cover
# those exact immutable refs rather than a historical release.
env_refs={name:os.getenv(name,'').strip() for name in IMAGE_VARS if os.getenv(name,'').strip()}
if env_refs:
    evidence_refs={str(x.get('name')):str(x.get('ref')) for x in data.get('releaseImages',[]) if isinstance(x,dict)}
    for name,ref in env_refs.items():
        if evidence_refs.get(name)!=ref: errors.append(f'evidence release image mismatch:{name}')

report={
    'status':'PASS' if not errors else 'FAIL',
    'schemaVersion':SCHEMA,
    'candidateCommit':data.get('candidateCommit'),
    'requiredGates':list(REQUIRED_GATES),
    'errors':errors,
    'evidenceFile':str(path),
    'productionHomologated':not errors,
}
print(json.dumps(report,indent=2,ensure_ascii=False))
if errors: raise SystemExit(1)
