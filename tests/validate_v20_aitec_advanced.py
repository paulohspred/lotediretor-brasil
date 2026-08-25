from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
unit_solver = (root / 'services/aitec-engine/app/unit_solver.py').read_text()
terrain_solver = (root / 'services/aitec-engine/app/terrain_solver.py').read_text()
building_solver = (root / 'services/aitec-engine/app/building_solver.py').read_text()
basement_solver = (root / 'services/aitec-engine/app/basement_parking_solver.py').read_text()
dockerfile = (root / 'services/aitec-engine/Dockerfile').read_text()

for token in ["DESIGN_DNA_VERSION = 'aitec-design-dna-v20.1'", "SOLVER_ID = 'conceptual-unit-distribution-v20.1'", 'solve_unit_distribution', 'compare_designs', 'content_fingerprint', 'lineage_fingerprint', 'parent_content_fingerprint', 'lock_fingerprint', 'locked_keys', 'PROGRAM_MIN_UNITS', 'UNIT_MIN:', 'UNIT_MAX:']:
    assert token in unit_solver, token
for token in ["TERRAIN_SOLVER_VERSION = 'aitec-terrain-v20.1'", 'build_tin', 'contour_segments', 'plateau_candidates', 'cut_fill_against_pad', 'analyze_terrain', 'triangulate(points)', 'slope_percent', 'aspect_deg']:
    assert token in terrain_solver, token
for token in ["BUILDING_SOLVER_VERSION = 'aitec-building-v20.1'", 'solve_building_system', 'CORE_FIT:', 'VERTICAL_COMPONENTS_FIT:', 'NET_FLOOR_AREA_POSITIVE:', 'vertical_components', 'core_geometry', 'circulation_geometry']:
    assert token in building_solver, token
for token in ["BASEMENT_PARKING_VERSION = 'aitec-basement-parking-v20.1'", 'solve_basement_parking', 'RAMP_REQUIRED', 'RAMP_MAX_SLOPE', 'PARKING_TOTAL_MIN', 'PARKING_ACCESSIBLE_MIN', 'PARKING_EV_MIN', 'column_spacing_x_m', 'accessible_ev_overlap']:
    assert token in basement_solver, token

for source, non_claims in [
    (unit_solver, ['não gera planta arquitetônica', 'Não inventa fachada', 'Locks preservam contagens exatas']),
    (terrain_solver, ['não inventa DEM/topografia', 'Não substitui levantamento topográfico', 'não inclui empolamento']),
    (building_solver, ['o solver não inventa requisitos normativos', 'Não substitui projeto arquitetônico']),
    (basement_solver, ['does not infer local parking', 'não constituem projeto estrutural', 'não verifica manobra por swept-path']),
]:
    for token in non_claims:
        assert token in source, token

assert 'COPY services/aitec-engine/app ./app' in dockerfile
for test in ['tests/test_v20_aitec_unit_solver.py','tests/test_v20_aitec_terrain_tin.py','tests/test_v20_aitec_building_solver.py','tests/test_v20_aitec_basement_parking.py']:
    subprocess.run(['python', test], check=True)
print('v20 A.I TEC Unit Solver/Design DNA + TIN terrain + Building Solver + basement parking contracts OK')
