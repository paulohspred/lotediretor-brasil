#!/usr/bin/env bash
set -euo pipefail
python tests/test_solar_domain.py
python tests/test_aitec_domain.py
python tests/test_data_connectors.py
python tests/validate_v8_contracts.py
python -m py_compile $(find services workers tests -name '*.py' -not -path '*/__pycache__/*')
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
const fs=require('fs'),path=require('path'),ts=require('typescript');let files=[];function walk(d){for(const e of fs.readdirSync(d,{withFileTypes:true})){if(['node_modules','.git'].includes(e.name))continue;const p=path.join(d,e.name);if(e.isDirectory())walk(p);else if(/\.(ts|tsx)$/.test(e.name))files.push(p)}}walk('.');let bad=[];for(const f of files){const sf=ts.createSourceFile(f,fs.readFileSync(f,'utf8'),ts.ScriptTarget.Latest,true,f.endsWith('.tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);if(sf.parseDiagnostics.length)bad.push(f)}console.log('TS/TSX parsed',files.length);if(bad.length){console.error('TS parse errors',bad);process.exit(1)}
JS
bash -n ops/runtime/smoke.sh ops/rls/run.sh ops/backup/backup.sh ops/backup/restore-drill.sh start.sh validate-v8.sh
printf 'v8 static/domain/ops validation OK\n'
