#!/usr/bin/env bash
set -euo pipefail

# Retained regressions
python tests/test_solar_domain.py
python tests/test_solar_v18_layout.py
python tests/test_aitec_domain.py
python tests/test_data_connectors.py
python tests/test_source_readiness_v11.py
python tests/test_report_renderer_v12.py
python tests/test_report_renderer_v16.py
python tests/test_report_renderer_v18.py
python tests/validate_v15_territorial.py
python tests/test_v15_spatial_contract.py
python tests/validate_v16_report_property360.py
python tests/test_rural_export_v17.py
python tests/test_rural_renderer_v17.py
python tests/validate_v17_rural360.py
python tests/test_condo_candidates_v18.py
python tests/validate_v18_condo_solar.py

# v19 alpha safety + beta deepening
python tests/test_aitec_v19_constraints.py
python tests/validate_v19_ai_core.py
python tests/validate_v19_ai_evals.py
python tests/validate_v19_sao_paulo_lab.py
python tests/validate_v19_publication_scope.py
python tests/test_legal_v19_structure.py
python tests/validate_v19_territorial_safety.py
python tests/test_legal_v19_beta_conditions.py
python tests/validate_v19_beta_rule_conditions.py
python tests/validate_v19_beta_ai_temporal.py
python tests/validate_v19_beta_source_modes.py

python -m py_compile $(find services workers tests ops -name '*.py' -not -path '*/__pycache__/*')
python - <<'PY'
from pathlib import Path
import json,yaml
for p in Path('.').rglob('*'):
    if not p.is_file() or 'node_modules' in p.parts or '__pycache__' in p.parts: continue
    if p.suffix=='.json': json.loads(p.read_text())
    elif p.suffix in ('.yaml','.yml'): yaml.safe_load(p.read_text())
print('JSON/YAML OK')
PY

node - <<'JS'
const fs=require('fs'),path=require('path'),ts=require('typescript');let f=[];
(function w(d){for(const e of fs.readdirSync(d,{withFileTypes:true})){if(['node_modules','.git','__pycache__'].includes(e.name))continue;const p=path.join(d,e.name);e.isDirectory()?w(p):/\.(ts|tsx)$/.test(e.name)&&f.push(p)}})('.');
let b=[];for(const p of f){let sf=ts.createSourceFile(p,fs.readFileSync(p,'utf8'),ts.ScriptTarget.Latest,true,p.endsWith('.tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);if(sf.parseDiagnostics.length)b.push({p,d:sf.parseDiagnostics.map(x=>x.messageText)})}
console.log('TS/TSX parsed',f.length);if(b.length){console.error(JSON.stringify(b,null,2));process.exit(1)}
JS

bash -n $(find ops -name '*.sh' -type f | sort) validate-v19-beta.sh validate-v19.sh

python - <<'PY'
import json
from pathlib import Path
V='19.0.0-beta.1'
bad=[]
for p in [Path('package.json'),*Path('apps').glob('*/package.json'),*Path('services').glob('*/package.json'),*Path('packages').glob('*/package.json')]:
    d=json.loads(p.read_text())
    if d.get('version')!=V: bad.append(f'{p}:{d.get("version")}')
    for sec in ('dependencies','devDependencies','peerDependencies'):
        for k,v in d.get(sec,{}).items():
            if k.startswith('@lotediretor/') and v!=V: bad.append(f'{p}:{k}={v}')
if bad: raise SystemExit('VERSION DRIFT '+repr(bad))
assert Path('VERSION').read_text().strip()==V
assert "RELEASE = 'v19-beta'" in Path('services/platform-api/src/version.ts').read_text()
assert "RELEASE='v19-beta'" in Path('services/control-api/src/version.ts').read_text()
assert "const VERSION='19.0.0-beta.1'" in Path('services/ai-gateway/src/main.ts').read_text()
assert "version='19.0.0-beta.1'" in Path('services/solar-engine/app/main.py').read_text()
assert "version='19.0.0-beta.1'" in Path('services/aitec-engine/app/main.py').read_text()
assert "WORKER_VERSION='19.0.0-beta.1'" in Path('workers/reports/main.py').read_text()
assert "VERSION='19.0.0-beta.1'" in Path('workers/rural-monitor/main.py').read_text()
assert "VERSION='19.0.0-beta.1'" in Path('workers/rural-export/main.py').read_text()
assert "const VERSION='19.0.0-beta.1'" in Path('services/event-dispatcher/src/main.ts').read_text()
for p in ('services/platform-api/src/v8.metrics.controller.ts','services/control-api/src/v8.metrics.controller.ts'):
    assert 'version="19.0.0-beta.1"' in Path(p).read_text()
print('Current-facing package/runtime versions OK')
PY

python - <<'PY'
from pathlib import Path
s=Path('services/platform-api/src/app.module.ts').read_text()
for x in ['CondoModule','SolarModule']: assert x in s,x
m=Path('db/platform/migrations/180_v18_condo_solar.sql').read_text()
for x in ['condo.unit','condo.assembly','condo.maintenance_item','solar.surface','solar.layout_panel','solar.energy_balance','CONDO360_360','SOLAR360_360','FORCE ROW LEVEL SECURITY']: assert x in m,x
b=Path('db/platform/migrations/192_v19_beta_legal_conditions_uses.sql').read_text()
for x in ['legal.rule','extraction_metadata','source_article_id','planning.zone_use_permission']: assert x in b,x
print('v19-beta runtime/domain topology contracts OK')
PY

python - <<'PY'
from pathlib import Path
ci=Path('.github/workflows/ci.yml').read_text()
assert './validate-v19-beta.sh' in ci
for old in ('./validate-v13.sh','./validate-v18.sh'):
    assert old not in ci
for k in ('PLATFORM_DB_EVENT_PASSWORD','PLATFORM_DB_WORKER_PASSWORD','CONTROL_DB_WORKER_PASSWORD'):
    assert k in ci,k
assert './validate-v19-beta.sh' in Path('ops/release/gate.sh').read_text()
# Current UI must not advertise an older milestone.
for p in Path('apps').rglob('*.tsx'):
    txt=p.read_text()
    if 'v19-alpha' in txt or 'v18 ·' in txt or 'v17 ·' in txt:
        raise SystemExit(f'CURRENT UI VERSION DRIFT {p}')
print('release/CI/UI drift guards OK')
PY

echo 'v19-beta validation OK'
