#!/usr/bin/env bash
set -euo pipefail
python tests/test_solar_domain.py
python tests/test_aitec_domain.py
python tests/test_data_connectors.py
python tests/test_source_readiness_v11.py
python tests/test_report_renderer_v12.py
python tests/validate_v15_territorial.py
python tests/test_v15_spatial_contract.py
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
const fs=require('fs'),path=require('path'),ts=require('typescript');let f=[];(function w(d){for(const e of fs.readdirSync(d,{withFileTypes:true})){if(['node_modules','.git'].includes(e.name))continue;const p=path.join(d,e.name);e.isDirectory()?w(p):/\.(ts|tsx)$/.test(e.name)&&f.push(p)}})('.');let b=[];for(const p of f){let sf=ts.createSourceFile(p,fs.readFileSync(p,'utf8'),ts.ScriptTarget.Latest,true,p.endsWith('.tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);if(sf.parseDiagnostics.length)b.push({p,d:sf.parseDiagnostics.map(x=>x.messageText)})}console.log('TS/TSX parsed',f.length);if(b.length){console.error(b);process.exit(1)}
JS
bash -n $(find ops -name '*.sh' -type f | sort) validate-v15.sh
python - <<'PY'
import json
from pathlib import Path
bad=[]
for p in [Path('package.json'),*Path('apps').glob('*/package.json'),*Path('services').glob('*/package.json'),*Path('packages').glob('*/package.json')]:
 d=json.loads(p.read_text());
 if d.get('version')!='15.0.0':bad.append(f'{p}:{d.get("version")}')
if bad:raise SystemExit('VERSION DRIFT '+repr(bad))
assert "RELEASE = 'v15'" in Path('services/platform-api/src/version.ts').read_text()
print('Current-facing package versions OK')
PY
echo 'v15 territorial validation OK'
