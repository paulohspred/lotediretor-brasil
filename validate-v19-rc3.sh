#!/usr/bin/env bash
set -euo pipefail

# Full retained regression surface.
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

# v19 foundation + RC deepening.
python tests/test_aitec_v19_constraints.py
python tests/validate_v19_ai_core.py
python tests/validate_v19_ai_evals.py
python tests/validate_v19_sao_paulo_lab.py
python tests/test_sao_paulo_v19_rc3_inspection_tooling.py
python tests/validate_v19_publication_scope.py
python tests/test_legal_v19_structure.py
python tests/validate_v19_territorial_safety.py
python tests/test_legal_v19_beta_conditions.py
python tests/validate_v19_beta_rule_conditions.py
python tests/validate_v19_beta_ai_temporal.py
python tests/validate_v19_beta_source_modes.py
python tests/validate_v19_rc_ai_knowledge.py
python tests/validate_v19_rc_ai_registry.py
python tests/validate_v19_rc_ai_high_risk.py
python tests/validate_v19_rc_ai_bitemporal.py
python tests/test_document_chunks_v19_rc.py
python tests/test_aitec_v19_rc_site_solver.py
python tests/test_aitec_v19_rc2_parking_geometry.py
python tests/test_aitec_v19_rc3_access_branch.py
python tests/test_aitec_v19_rc3_program_terrain_building.py
python tests/test_solar_v19_rc3_electrical.py

python -m py_compile $(find services workers tests ops -name '*.py' -not -path '*/__pycache__/*')
python - <<'PY'
from pathlib import Path
import json,yaml

class ComposeSafeLoader(yaml.SafeLoader):
    pass

def compose_tag(loader, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    raise TypeError(f'Unsupported YAML node for Compose tag: {type(node).__name__}')

# Docker Compose defines these tags for merge semantics. They are valid Compose
# YAML and must not make the generic syntax guard reject release overlays.
ComposeSafeLoader.add_constructor('!reset', compose_tag)
ComposeSafeLoader.add_constructor('!override', compose_tag)

for p in Path('.').rglob('*'):
    if not p.is_file() or 'node_modules' in p.parts or '__pycache__' in p.parts: continue
    if p.suffix=='.json': json.loads(p.read_text())
    elif p.suffix in ('.yaml','.yml'): yaml.load(p.read_text(), Loader=ComposeSafeLoader)
print('JSON/YAML OK')
PY

node - <<'JS'
const fs=require('fs'),path=require('path'),ts=require('typescript');let f=[];
(function w(d){for(const e of fs.readdirSync(d,{withFileTypes:true})){if(['node_modules','.git','__pycache__'].includes(e.name))continue;const p=path.join(d,e.name);e.isDirectory()?w(p):/\.(ts|tsx)$/.test(e.name)&&f.push(p)}})('.');
let b=[];for(const p of f){let sf=ts.createSourceFile(p,fs.readFileSync(p,'utf8'),ts.ScriptTarget.Latest,true,p.endsWith('.tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);if(sf.parseDiagnostics.length)b.push({p,d:sf.parseDiagnostics.map(x=>x.messageText)})}
console.log('TS/TSX parsed',f.length);if(b.length){console.error(JSON.stringify(b,null,2));process.exit(1)}
JS

bash -n $(find ops -name '*.sh' -type f | sort) validate-v19-rc.sh validate-v19-rc2.sh validate-v19-rc3.sh validate-v19.sh

python - <<'PY'
import json
from pathlib import Path
V='19.0.0-rc.3'
bad=[]
for p in [Path('package.json'),*Path('apps').glob('*/package.json'),*Path('services').glob('*/package.json'),*Path('packages').glob('*/package.json')]:
    d=json.loads(p.read_text())
    if d.get('version')!=V: bad.append(f'{p}:{d.get("version")}')
    for sec in ('dependencies','devDependencies','peerDependencies'):
        for k,v in d.get(sec,{}).items():
            if k.startswith('@lotediretor/') and v!=V: bad.append(f'{p}:{k}={v}')
if bad: raise SystemExit('VERSION DRIFT '+repr(bad))
assert Path('VERSION').read_text().strip()==V
assert "RELEASE = 'v19-rc3'" in Path('services/platform-api/src/version.ts').read_text()
assert "RELEASE='v19-rc3'" in Path('services/control-api/src/version.ts').read_text()
for p in ('services/platform-api/src/v8.metrics.controller.ts','services/control-api/src/v8.metrics.controller.ts'):
    assert 'version="19.0.0-rc.3"' in Path(p).read_text()
print('Current-facing package/runtime versions OK')
PY

python - <<'PY'
from pathlib import Path
m=Path('db/platform/migrations/193_v19_rc_ai_knowledge_plane.sql').read_text()
for x in ['retrieval_allowed','visibility','document_version_id','trg_ai_reindex_legal_version','FORCE ROW LEVEL SECURITY']:assert x in m,x
a=Path('db/platform/migrations/194_v19_rc_aitec_site_solver.sql').read_text()
for x in ['aitec.solution','aitec.geometry_object','aitec.violation','aitec.solution_lock','FORCE ROW LEVEL SECURITY']:assert x in a,x
r=Path('db/platform/migrations/195_v19_rc3_aitec_deepening.sql').read_text()
for x in ['aitec.analysis_result','aitec_artifact_solution_fk','aitec_solution_project_tenant_fk','FORCE ROW LEVEL SECURITY']:assert x in r,x
solar=Path('db/platform/migrations/196_v19_rc3_solar_electrical.sql').read_text()
for x in ['solar.electrical_design','solar_regulation_global_code_date_uidx','FORCE ROW LEVEL SECURITY']:assert x in solar,x
api=Path('services/platform-api/src/v7.controller.ts').read_text()
for x in ['aitec/projects/:id/solutions/generate','aitec/projects/:id/solutions','aitec/solutions/:solutionId','aitec.solutions.generated','aitec/solutions/:solutionId/locks','aitec/solutions/:solutionId/branch','export-geojson','export-csv']:assert x in api,x
print('v19-rc3 domain topology contracts OK')
PY

python - <<'PY'
from pathlib import Path
ci=Path('.github/workflows/ci.yml').read_text();gate=Path('ops/release/gate.sh').read_text()
assert './validate-v19-rc3.sh' in ci and './validate-v19-rc3.sh' in gate
for old in ('./validate-v13.sh','./validate-v18.sh','./validate-v19-beta.sh','./validate-v19-rc.sh','./validate-v19-rc2.sh'):
    assert old not in ci
for k in ('PLATFORM_DB_EVENT_PASSWORD','PLATFORM_DB_WORKER_PASSWORD','CONTROL_DB_WORKER_PASSWORD'):
    assert k in ci,k
for p in Path('apps').rglob('*.tsx'):
    txt=p.read_text()
    if 'v19-alpha' in txt or 'v19-beta' in txt or 'v18 ·' in txt or 'v17 ·' in txt:
        raise SystemExit(f'CURRENT UI VERSION DRIFT {p}')
print('release/CI/UI drift guards OK')
PY

echo 'v19-rc3 validation OK'
