#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

artifact = Path(sys.argv[1]).resolve()
requested_status = sys.argv[2] if len(sys.argv) > 2 else 'UNKNOWN'
profile = sys.argv[3] if len(sys.argv) > 3 else 'ci'

required_gates = [
    'production_parity','staging_parity','immutable_release','rollback_contract',
    'compose_model','build_images','stack_health','runtime_smoke','aitec_runtime',
    'rls_isolation','privacy_lgpd','municipality_factory','ai_retrieval',
    'critical_fixture_seed','browser_critical','security_baseline','load_profile',
    'fault_injection','observability','backup','restore_dr',
]

external_gates = [
    {'gate':'independent_pentest','status':'NOT_HOMOLOGATED','reason':'requires independent authorized assessment and closure of all Critical/High findings'},
    {'gate':'production_like_staging','status':'NOT_HOMOLOGATED','reason':'structural staging parity is tested locally, but deployed cloud/network/provider equivalence still requires final-environment evidence'},
    {'gate':'live_canary_rollback','status':'NOT_HOMOLOGATED','reason':'repository contains executable canary/rollback contracts, but live execution is environment evidence'},
    {'gate':'production_ha_dr','status':'NOT_HOMOLOGATED','reason':'local DR evidence is synthetic; production RPO/RTO and PITR/failover require the final environment'},
    {'gate':'official_sources_and_providers','status':'NOT_HOMOLOGATED','reason':'live credentials, licenses, municipal/official datasets and provider evidence remain external'},
    {'gate':'professional_institutional_review','status':'NOT_HOMOLOGATED','reason':'legal/architecture/engineering/fiscal/institutional approvals cannot be synthesized by local automation'},
    {'gate':'main_branch_protection','status':'NOT_HOMOLOGATED','reason':'requires repository administration/ruleset configuration outside this qualification run'},
]


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def file_check(name: str, path: Path, validator=None):
    if not path.exists() or not path.is_file():
        try: display=str(path.relative_to(artifact))
        except Exception: display=str(path)
        return {'check':name,'status':'FAIL','path':display,'reason':'missing'}
    value = read_json(path) if path.suffix == '.json' else None
    if validator:
        try:
            ok, detail = validator(value, path)
        except Exception as exc:
            ok, detail = False, f'validator_error:{exc}'
        return {'check':name,'status':'PASS' if ok else 'FAIL','path':str(path.relative_to(artifact)),'detail':detail}
    return {'check':name,'status':'PASS','path':str(path.relative_to(artifact)),'bytes':path.stat().st_size}


gates = {}
ledger = artifact / 'gate-status.tsv'
if ledger.exists():
    for line in ledger.read_text(encoding='utf-8',errors='replace').splitlines():
        if not line.strip() or line.startswith('gate\t'): continue
        parts=line.split('\t')
        if len(parts) < 5: continue
        gate,status,started,completed,duration = parts[:5]
        try: duration_value=float(duration) if duration else None
        except ValueError: duration_value=None
        gates[gate]={'gate':gate,'status':status,'startedAtUtc':started,'completedAtUtc':completed,'durationSeconds':duration_value}

local_gate_results=[gates.get(gate,{'gate':gate,'status':'MISSING'}) for gate in required_gates]

checks=[]
checks.append(file_check('qualification_status',artifact/'qualification.json',lambda v,p:(isinstance(v,dict) and v.get('status')==requested_status,f"status={v.get('status') if isinstance(v,dict) else None}")))
checks.append(file_check('production_parity',artifact/'production-parity.json',lambda v,p:(isinstance(v,dict) and v.get('status')=='PASS',f"errors={v.get('errors') if isinstance(v,dict) else None}")))
checks.append(file_check('staging_parity',artifact/'staging-parity.json',lambda v,p:(isinstance(v,dict) and v.get('status')=='PASS' and v.get('classification')=='STRUCTURAL_STAGING_PARITY_CONTRACT_NOT_DEPLOYED_STAGING_EVIDENCE',f"classification={v.get('classification') if isinstance(v,dict) else None}")))
checks.append(file_check('immutable_release',artifact/'immutable-release.json',lambda v,p:(isinstance(v,dict) and v.get('status')=='PASS' and int(v.get('promotedServices',0))>=20,f"promotedServices={v.get('promotedServices') if isinstance(v,dict) else None}")))
checks.append(file_check('rollback_contract',artifact/'rollback-contract.txt',lambda v,p:(bool(p.read_text(encoding='utf-8',errors='replace').strip()),'rollback self-test output present')))
checks.append(file_check('platform_migrations',artifact/'platform-migrations.txt',lambda v,p:(bool(p.read_text().strip()),'non-empty migration ledger')))
checks.append(file_check('control_migrations',artifact/'control-migrations.txt',lambda v,p:(bool(p.read_text().strip()),'non-empty migration ledger')))
checks.append(file_check('playwright_results',artifact/'browser'/'playwright-results.json',lambda v,p:(isinstance(v,dict) and int((v.get('stats') or {}).get('unexpected',0))==0 and int((v.get('stats') or {}).get('expected',0))>0,f"stats={(v or {}).get('stats') if isinstance(v,dict) else None}")))
checks.append(file_check('k6_summary',artifact/'load'/'k6-summary.json'))
checks.append(file_check('security_baseline',artifact/'security'/'result.json',lambda v,p:(isinstance(v,dict) and v.get('status')=='PASS',f"status={v.get('status') if isinstance(v,dict) else None}")))
checks.append(file_check('observability_gate',artifact/'observability'/'observability-gate.json',lambda v,p:(isinstance(v,dict) and v.get('status')=='PASS',f"status={v.get('status') if isinstance(v,dict) else None}")))
checks.append(file_check('resilience_events',artifact/'resilience'/'events.tsv',lambda v,p:(len([x for x in p.read_text().splitlines() if x.strip()])>=6,'fault/recovery event ledger present')))

dr_files=sorted((artifact/'dr').glob('dr-*.json')) if (artifact/'dr').exists() else []
if dr_files:
    checks.append(file_check('dr_evidence',dr_files[-1],lambda v,p:(isinstance(v,dict) and v.get('status')=='PASS' and v.get('classification')=='LOCAL_SYNTHETIC_DR_EVIDENCE_NOT_PRODUCTION_HOMOLOGATION' and isinstance(v.get('rpoSeconds'),int) and isinstance(v.get('rtoSeconds'),int),f"rpo={v.get('rpoSeconds') if isinstance(v,dict) else None}s rto={v.get('rtoSeconds') if isinstance(v,dict) else None}s")))
else:
    checks.append({'check':'dr_evidence','status':'FAIL','reason':'missing runtime-artifacts/dr/dr-*.json'})

checks.append(file_check('opensearch_health',artifact/'opensearch-health.json',lambda v,p:(isinstance(v,dict) and str(v.get('status','')).lower() in {'green','yellow'},f"cluster_status={v.get('status') if isinstance(v,dict) else None}")))
for name in ('ld-ai-a.json','ld-ai-b-leak.json','ld-ai-public.json','ld-ai-future.json'):
    checks.append(file_check(f'ai_runtime_{name}',artifact/name))

local_gates_ok = all(x.get('status')=='PASS' for x in local_gate_results)
artifact_checks_ok = all(x.get('status')=='PASS' for x in checks)
local_status = 'PASS' if requested_status=='PASS' and local_gates_ok and artifact_checks_ok else 'FAIL'

report={
    'schemaVersion':'lotediretor-local-qualification-v1',
    'generatedAtUtc':datetime.now(timezone.utc).isoformat(),
    'profile':profile,
    'requestedQualificationStatus':requested_status,
    'localQualificationStatus':local_status,
    'productionHomologated':False,
    'localGates':local_gate_results,
    'artifactChecks':checks,
    'externalFinalGates':external_gates,
    'decision':{
        'readyForCortexDebugging':True,
        'readyToClaimLocalQualification':local_status=='PASS',
        'readyToClaimProductionHomologation':False,
    },
}

json_path=artifact/'qualification-report.json'
json_path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

md=['# LoteDiretor — Local Qualification Report','',f'- Generated: `{report["generatedAtUtc"]}`',f'- Profile: `{profile}`',f'- Local qualification: **{local_status}**','- Production homologated: **NO**','','## Local gates','','| Gate | Status | Duration (s) |','|---|---:|---:|']
for item in local_gate_results: md.append(f'| `{item["gate"]}` | {item.get("status")} | {item.get("durationSeconds","")} |')
md += ['','## Evidence checks','','| Evidence | Status | Detail |','|---|---:|---|']
for item in checks:
    detail=item.get('detail') or item.get('reason') or item.get('path') or ''
    md.append(f'| `{item["check"]}` | {item.get("status")} | {str(detail).replace("|","/")} |')
md += ['','## External/final gates','','| Gate | Status | Reason |','|---|---:|---|']
for item in external_gates: md.append(f'| `{item["gate"]}` | {item["status"]} | {item["reason"]} |')
md += ['','`productionHomologated` remains `false` until the external/final gates have real environment evidence.']
(artifact/'qualification-report.md').write_text('\n'.join(md)+'\n',encoding='utf-8')

print(json_path)
if requested_status=='PASS' and local_status!='PASS':
    raise SystemExit('qualification report found missing/failed local gate evidence')
