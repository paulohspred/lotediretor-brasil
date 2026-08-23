$ErrorActionPreference = "Stop"
python tests/test_solar_domain.py
python tests/test_aitec_domain.py
python tests/test_data_connectors.py
python tests/validate_v8_contracts.py
python -m compileall -q services workers tests
python -c "import pathlib,json,yaml; [(json.loads(p.read_text(encoding='utf-8')) if p.suffix=='.json' else yaml.safe_load(p.read_text(encoding='utf-8'))) for p in pathlib.Path('.').rglob('*') if p.is_file() and p.suffix in ('.json','.yaml','.yml') and 'node_modules' not in p.parts]; print('JSON/YAML OK')"
Write-Host "v8 static/domain/ops validation OK"
