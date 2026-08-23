#!/usr/bin/env bash
set -euo pipefail
python tests/test_solar_domain.py
python tests/test_aitec_domain.py
python tests/test_data_connectors.py
python tests/test_source_readiness_v11.py
python tests/test_report_renderer_v12.py
python tests/validate_v14_contracts.py
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
bash -n $(find ops -name '*.sh' -type f | sort) validate-v14.sh
python - <<'PY'
import yaml
base=yaml.safe_load(open('docker-compose.yml'));prod=yaml.safe_load(open('docker-compose.production.yml'))
assert 'platform-migrate' in base['services'] and 'control-migrate' in base['services']
assert base['services']['platform-db-role-init']['depends_on']['platform-migrate']['condition']=='service_completed_successfully'
print('Compose YAML/startup ordering OK')
PY
# Current-facing version drift guard. Historical migrations/tests/docs may keep their original version labels.
python - <<'PY'
from pathlib import Path
import json,re,sys
bad=[]
for p in [Path('package.json'),*Path('apps').glob('*/package.json'),*Path('services').glob('*/package.json'),*Path('packages').glob('*/package.json')]:
 d=json.loads(p.read_text());
 if d.get('version')!='14.0.0':bad.append(f'{p}:{d.get("version")}')
for p in [Path('services/solar-engine/app/main.py'),Path('services/aitec-engine/app/main.py'),Path('services/ai-gateway/src/main.ts'),Path('services/control-api/src/version.ts'),Path('services/platform-api/src/version.ts')]:
 t=p.read_text()
 if '14.0.0' not in t and "'v14'" not in t:bad.append(str(p))
if bad:print('VERSION DRIFT',bad,file=sys.stderr);sys.exit(1)
print('Current-facing version drift OK')
PY
echo 'v14 static structural validation OK'
