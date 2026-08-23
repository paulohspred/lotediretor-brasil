#!/usr/bin/env sh
set -eu
python tests/test_solar_domain.py
python tests/test_aitec_domain.py
python tests/validate_v7_contracts.py
python -m py_compile $(find services workers tests -name '*.py')
python - <<'PY'
from pathlib import Path
import json,yaml
for p in Path('.').rglob('*'):
    if not p.is_file() or 'node_modules' in p.parts: continue
    if p.suffix=='.json':json.loads(p.read_text())
    elif p.suffix in ('.yaml','.yml'):yaml.safe_load(p.read_text())
print('JSON/YAML OK')
PY
printf 'v7 domain/static validation OK\n'
