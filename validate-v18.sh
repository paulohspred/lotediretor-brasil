#!/usr/bin/env bash
set -euo pipefail
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
python -m py_compile $(find services workers tests ops -name '*.py' -not -path '*/__pycache__/*')
python - <<'PY'
from pathlib import Path
import json,yaml
for p in Path('.').rglob('*'):
 if not p.is_file() or 'node_modules' in p.parts or '__pycache__' in p.parts:continue
 if p.suffix=='.json':json.loads(p.read_text())
 elif p.suffix in ('.yaml','.yml'):yaml.safe_load(p.read_text())
print('JSON/YAML OK')
PY
node - <<'JS'
const fs=require('fs'),path=require('path'),ts=require('typescript');let f=[];(function w(d){for(const e of fs.readdirSync(d,{withFileTypes:true})){if(['node_modules','.git'].includes(e.name))continue;const p=path.join(d,e.name);e.isDirectory()?w(p):/\.(ts|tsx)$/.test(e.name)&&f.push(p)}})('.');let b=[];for(const p of f){let sf=ts.createSourceFile(p,fs.readFileSync(p,'utf8'),ts.ScriptTarget.Latest,true,p.endsWith('.tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);if(sf.parseDiagnostics.length)b.push({p,d:sf.parseDiagnostics.map(x=>x.messageText)})}console.log('TS/TSX parsed',f.length);if(b.length){console.error(JSON.stringify(b,null,2));process.exit(1)}
JS
bash -n $(find ops -name '*.sh' -type f | sort) validate-v18.sh
python - <<'PY'
import json
from pathlib import Path
bad=[]
for p in [Path('package.json'),*Path('apps').glob('*/package.json'),*Path('services').glob('*/package.json'),*Path('packages').glob('*/package.json')]:
 d=json.loads(p.read_text());
 if d.get('version')!='18.0.0':bad.append(f'{p}:{d.get("version")}')
if bad:raise SystemExit('VERSION DRIFT '+repr(bad))
assert Path('VERSION').read_text().strip()=='18.0.0'
assert "RELEASE = 'v18'" in Path('services/platform-api/src/version.ts').read_text()
assert "RELEASE='v18'" in Path('services/control-api/src/version.ts').read_text()
assert "const VERSION='18.0.0'" in Path('services/ai-gateway/src/main.ts').read_text()
assert "version='18.0.0'" in Path('services/solar-engine/app/main.py').read_text()
assert "version='18.0.0'" in Path('services/aitec-engine/app/main.py').read_text()
assert "WORKER_VERSION='18.0.0'" in Path('workers/reports/main.py').read_text()
assert "VERSION='18.0.0'" in Path('workers/rural-monitor/main.py').read_text()
assert "VERSION='18.0.0'" in Path('workers/rural-export/main.py').read_text()
for p in Path('apps').rglob('*.tsx'):
 txt=p.read_text()
 if 'v17' in txt:raise SystemExit(f'CURRENT UI VERSION DRIFT {p}')
 if '\nTS\ncat > ' in txt:raise SystemExit(f'HEREDOC CONTAMINATION {p}')
print('Current-facing package/runtime versions OK')
PY
python - <<'PY'
from pathlib import Path
s=Path('services/platform-api/src/app.module.ts').read_text()
for x in ['CondoModule','SolarModule']:assert x in s,x
m=Path('db/platform/migrations/180_v18_condo_solar.sql').read_text()
for x in ['condo.unit','condo.assembly','condo.maintenance_item','solar.surface','solar.layout_panel','solar.energy_balance','CONDO360_360','SOLAR360_360','FORCE ROW LEVEL SECURITY']:assert x in m,x
print('v18 runtime/domain topology contracts OK')
PY
python - <<'PY2'
from pathlib import Path
import json
for p in [Path('apps/client-web/package.json'),Path('apps/site-web/package.json'),Path('apps/admin-web/package.json')]:
 d=json.loads(p.read_text())
 for sec in ('dependencies','devDependencies','peerDependencies'):
  for k,v in d.get(sec,{}).items():
   if k.startswith('@lotediretor/') and v!='18.0.0':
    raise SystemExit(f'INTERNAL WORKSPACE VERSION DRIFT {p} {k}={v}')
ci=Path('.github/workflows/ci.yml').read_text()
assert './validate-v18.sh' in ci and './validate-v13.sh' not in ci
for k in ('PLATFORM_DB_EVENT_PASSWORD','PLATFORM_DB_WORKER_PASSWORD','CONTROL_DB_WORKER_PASSWORD'):
 assert k in ci,k
assert './validate-v18.sh' in Path('ops/release/gate.sh').read_text()
assert "const VERSION='18.0.0'" in Path('services/event-dispatcher/src/main.ts').read_text()
for p in ('services/platform-api/src/v8.metrics.controller.ts','services/control-api/src/v8.metrics.controller.ts'):
 assert 'version="18.0.0"' in Path(p).read_text()
print('baseline release/CI/workspace drift guards OK')
PY2
echo 'v18 validation OK'
