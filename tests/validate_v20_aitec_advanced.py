from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
unit_solver = (root / 'services/aitec-engine/app/unit_solver.py').read_text()
terrain_solver = (root / 'services/aitec-engine/app/terrain_solver.py').read_text()
building_solver = (root / 'services/aitec-engine/app/building_solver.py').read_text()
basement_solver = (root / 'services/aitec-engine/app/basement_parking_solver.py').read_text()
room_solver = (root / 'services/aitec-engine/app/room_solver.py').read_text()
road_solver = (root / 'services/aitec-engine/app/road_engineering_solver.py').read_text()
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

for non_claim in ['não gera planta arquitetônica','Não inventa fachada','Locks preservam contagens exatas']:
    assert non_claim in unit_solver, non_claim

for token in [
    "TERRAIN_SOLVER_VERSION = 'aitec-terrain-v20.1'",'build_tin','contour_segments','plateau_candidates','cut_fill_against_pad','analyze_terrain','triangulate(points)','slope_percent','aspect_deg','exact integration of piecewise-linear TIN against horizontal pad',
]:
    assert token in terrain_solver, token
for non_claim in ['não inventa DEM/topografia','Não substitui levantamento topográfico','não inclui empolamento']:
    assert non_claim in terrain_solver, non_claim

for token in [
    "BUILDING_SOLVER_VERSION = 'aitec-building-v20.1'",'solve_building_system','CORE_FIT:','VERTICAL_COMPONENTS_FIT:','NET_FLOOR_AREA_POSITIVE:','vertical_components','core_geometry','circulation_geometry',
]:
    assert token in building_solver, token
for non_claim in ['o solver não inventa requisitos normativos','não comprovam incêndio, acessibilidade, estrutura, egress','Não substitui projeto arquitetônico']:
    assert non_claim in building_solver, non_claim

for token in [
    "BASEMENT_PARKING_VERSION = 'aitec-basement-parking-v20.1'",'solve_basement_parking','RAMP_REQUIRED','RAMP_MAX_SLOPE','PARKING_TOTAL_MIN','PARKING_ACCESSIBLE_MIN','PARKING_EV_MIN','column_spacing_x_m','accessible_ev_overlap',
]:
    assert token in basement_solver, token
for non_claim in ['não infer local parking, PCD, EV, ramp, fire or structural requirements','não constituem projeto estrutural','não verifica manobra por swept-path']:
    assert non_claim in basement_solver, non_claim

for token in [
    "ROOM_SOLVER_VERSION = 'aitec-room-graph-v20.1'",'solve_unit_room_graph','ROOM_MIN_AREA:','ROOM_MIN_WIDTH:','ROOM_MIN_DEPTH:','ADJACENCY:','INTERNAL_OPENING:','EXTERIOR_OPENING:','ROOMS_NO_OVERLAP','ROOMS_COVER_UNIT',
]:
    assert token in room_solver, token
for non_claim in ['does not infer local','não é projeto executivo','não inventa norma local','Não resolve mobiliário, estrutura, MEP, incêndio, acessibilidade']:
    assert non_claim in room_solver, non_claim

for token in [
    "ROAD_SOLVER_VERSION = 'aitec-road-engineering-v20.1'",'evaluate_road_engineering','ROAD_SURFACE_INSIDE_PARCEL','ACCESS_AT_BOUNDARY','ROAD_MIN_TURN_RADIUS','ROAD_GRADE_DATA','ROAD_MAX_GRADE','EMERGENCY_MIN_WIDTH','EMERGENCY_TURNAROUND_INSIDE_PARCEL',
]:
    assert token in road_solver, token
for non_claim in ['does not infer local','não gera projeto viário executivo','nenhuma norma local é inferida','Não verifica swept-path']:
    assert non_claim in road_solver, non_claim

assert 'COPY services/aitec-engine/app ./app' in dockerfile
for test in [
    'tests/test_v20_aitec_unit_solver.py',
    'tests/test_v20_aitec_terrain_tin.py',
    'tests/test_v20_aitec_building_solver.py',
    'tests/test_v20_aitec_basement_parking.py',
    'tests/test_v20_aitec_room_graph.py',
    'tests/test_v20_aitec_road_engineering.py',
]:
    subprocess.run(['python', test], check=True)
print('v20 A.I TEC advanced deterministic solver contracts OK')
