from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
unit_solver = (root / 'services/aitec-engine/app/unit_solver.py').read_text()
terrain_solver = (root / 'services/aitec-engine/app/terrain_solver.py').read_text()
building_solver = (root / 'services/aitec-engine/app/building_solver.py').read_text()
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
    assert token in unit_solver, token

for non_claim in [
    'não gera planta arquitetônica',
    'Não inventa fachada',
    'Locks preservam contagens exatas',
]:
    assert non_claim in unit_solver, non_claim

for token in [
    "TERRAIN_SOLVER_VERSION = 'aitec-terrain-v20.1'",
    'build_tin',
    'contour_segments',
    'plateau_candidates',
    'cut_fill_against_pad',
    'analyze_terrain',
    'triangulate(points)',
    'slope_percent',
    'aspect_deg',
    'exact integration of piecewise-linear TIN against horizontal pad',
]:
    assert token in terrain_solver, token

for non_claim in [
    'não inventa DEM/topografia',
    'Não substitui levantamento topográfico',
    'não inclui empolamento',
]:
    assert non_claim in terrain_solver, non_claim

for token in [
    "BUILDING_SOLVER_VERSION = 'aitec-building-v20.1'",
    'solve_building_system',
    'CORE_FIT:',
    'VERTICAL_COMPONENTS_FIT:',
    'NET_FLOOR_AREA_POSITIVE:',
    'vertical_components',
    'core_geometry',
    'circulation_geometry',
]:
    assert token in building_solver, token

for non_claim in [
    'o solver não inventa requisitos normativos',
    'não comprovam incêndio, acessibilidade, estrutura, egress',
    'Não substitui projeto arquitetônico',
]:
    assert non_claim in building_solver, non_claim

assert 'COPY services/aitec-engine/app ./app' in dockerfile
subprocess.run(['python', 'tests/test_v20_aitec_unit_solver.py'], check=True)
subprocess.run(['python', 'tests/test_v20_aitec_terrain_tin.py'], check=True)
subprocess.run(['python', 'tests/test_v20_aitec_building_solver.py'], check=True)
print('v20 A.I TEC Unit Solver/Design DNA + TIN terrain + Building Solver contracts OK')
