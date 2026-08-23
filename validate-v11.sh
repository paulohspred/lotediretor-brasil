#!/usr/bin/env bash
set -euo pipefail
python tests/test_solar_domain.py
python tests/test_aitec_domain.py
python tests/test_data_connectors.py
python tests/test_source_readiness_v11.py
python tests/validate_v11_contracts.py
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
const fs=require('fs'),path=require('path'),ts=require('typescript');let f=[];(function w(d){for(const e of fs.readdirSync(d,{withFileTypes:true})){if(['node_modules','.git'].includes(e.name))continue;const p=path.join(d,e.name);e.isDirectory()?w(p):/\.(ts|tsx)$/.test(e.name)&&f.push(p)}})('.');let b=[];for(const p of f){let s=ts.createSourceFile(p,fs.readFileSync(p,'utf8'),ts.ScriptTarget.Latest,true,p.endsWith('.tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);if(s.parseDiagnostics.length)b.push(p)}console.log('TS/TSX parsed',f.length);if(b.length){console.error(b);process.exit(1)}
JS
bash -n ops/runtime/*.sh ops/rls/*.sh ops/backup/*.sh ops/db/*.sh validate-v11.sh
echo 'v11 static/domain/data-contract validation OK'
