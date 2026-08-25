from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
solver = (root / 'services/aitec-engine/app/unit_solver.py').read_text()
dockerfile = (root / 'services/aitec-engine/Dockerfile').read_text()

for token in [
    "DESIGN_DNA_VERSION = 'aitec-design-dna-v20.1'",
    "SOLVER_ID = 'conceptual-unit-distribution-v20.1'",
    'solve_unit_distribution',
    'compare_designs',
    'content_fingerprint',
    'lineage_fingerprint',
    'parent_content_fingerprint',
    'lock_fingerprint',
    'locked_keys',
    'PROGRAM_MIN_UNITS',
    'UNIT_MIN:',
    'UNIT_MAX:',
]:
    assert token in solver, token

for non_claim in [
    'não gera planta arquitetônica',
    'Não inventa fachada',
    'Locks preservam contagens exatas',
]:
    assert non_claim in solver, non_claim

assert 'COPY services/aitec-engine/app ./app' in dockerfile
subprocess.run(['python', 'tests/test_v20_aitec_unit_solver.py'], check=True)
print('v20 A.I TEC conceptual Unit Solver + Design DNA contracts OK')
