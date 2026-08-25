from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
unit_solver = (root / 'services/aitec-engine/app/unit_solver.py').read_text()
terrain_solver = (root / 'services/aitec-engine/app/terrain_solver.py').read_text()
building_solver = (root / 'services/aitec-engine/app/building_solver.py').read_text()
basement_solver = (root / 'services/aitec-engine/app/basement_parking_solver.py').read_text()
room_solver = (root / 'services/aitec-engine/app/room_solver.py').read_text()
road_solver = (root / 'services/aitec-engine/app/road_engineering_solver.py').read_text()
environment_solver = (root / 'services/aitec-engine/app/environment_solver.py').read_text()
finance_solver = (root / 'services/aitec-engine/app/finance_solver.py').read_text()
dockerfile = (root / 'services/aitec-engine/Dockerfile').read_text()

checks = [
    (unit_solver, ["DESIGN_DNA_VERSION = 'aitec-design-dna-v20.1'", "SOLVER_ID = 'conceptual-unit-distribution-v20.1'", 'solve_unit_distribution', 'compare_designs', 'content_fingerprint', 'lineage_fingerprint', 'parent_content_fingerprint', 'lock_fingerprint', 'locked_keys', 'PROGRAM_MIN_UNITS', 'UNIT_MIN:', 'UNIT_MAX:']),
    (terrain_solver, ["TERRAIN_SOLVER_VERSION = 'aitec-terrain-v20.1'", 'build_tin', 'contour_segments', 'plateau_candidates', 'cut_fill_against_pad', 'analyze_terrain', 'triangulate(points)', 'slope_percent', 'aspect_deg']),
    (building_solver, ["BUILDING_SOLVER_VERSION = 'aitec-building-v20.1'", 'solve_building_system', 'CORE_FIT:', 'VERTICAL_COMPONENTS_FIT:', 'NET_FLOOR_AREA_POSITIVE:']),
    (basement_solver, ["BASEMENT_PARKING_VERSION = 'aitec-basement-parking-v20.1'", 'solve_basement_parking', 'RAMP_REQUIRED', 'RAMP_MAX_SLOPE', 'PARKING_TOTAL_MIN', 'PARKING_ACCESSIBLE_MIN', 'PARKING_EV_MIN']),
    (room_solver, ["ROOM_SOLVER_VERSION = 'aitec-room-graph-v20.1'", 'solve_unit_room_graph', 'ROOM_MIN_AREA:', 'ROOM_MIN_WIDTH:', 'ROOM_MIN_DEPTH:', 'ADJACENCY:', 'INTERNAL_OPENING:', 'EXTERIOR_OPENING:', 'ROOMS_NO_OVERLAP', 'ROOMS_COVER_UNIT']),
    (road_solver, ["ROAD_SOLVER_VERSION = 'aitec-road-engineering-v20.1'", 'evaluate_road_engineering', 'ROAD_SURFACE_INSIDE_PARCEL', 'ACCESS_AT_BOUNDARY', 'ROAD_MIN_TURN_RADIUS', 'ROAD_GRADE_DATA', 'ROAD_MAX_GRADE', 'EMERGENCY_MIN_WIDTH']),
    (environment_solver, ["ENVIRONMENT_SOLVER_VERSION = 'aitec-environment-v20.1'", 'analyze_solar_exposure', 'analyze_daylight', 'analyze_noise', 'analyze_wind', 'analyze_environment', 'SOLAR_EXPOSURE_MIN', 'DAYLIGHT_PROXY_MIN', 'NOISE_MAX_DB', 'WIND_COMFORT_MAX_SPEED', "status = 'UNVERIFIED'"]),
    (finance_solver, ["FINANCE_SOLVER_VERSION = 'aitec-finance-v20.1'", 'calculate_project_finance', 'market_snapshot_id', 'cost_snapshot_id', 'MIN_PROJECT_MARGIN', 'MAX_TOTAL_COST', 'pareto_metrics', '_irr_monthly', '_npv']),
]
for source, tokens in checks:
    for token in tokens:
        assert token in source, token

for source, non_claims in [
    (unit_solver, ['não gera planta arquitetônica', 'Não inventa fachada']),
    (terrain_solver, ['não inventa DEM/topografia', 'Não substitui levantamento topográfico']),
    (building_solver, ['não inventa requisitos normativos', 'Não substitui projeto arquitetônico']),
    (basement_solver, ['não infer local parking', 'não constituem projeto estrutural']),
    (room_solver, ['não é projeto executivo', 'não inventa norma local']),
    (road_solver, ['não gera projeto viário executivo', 'nenhuma norma local é inferida']),
    (environment_solver, ['not irradiance or energy yield', 'não substitui CFD', 'UNVERIFIED']),
    (finance_solver, ['never invents unit prices', 'não inventa dados de mercado nem custo', 'Não substitui orçamento executivo']),
]:
    for token in non_claims:
        assert token in source, token

assert 'COPY services/aitec-engine/app ./app' in dockerfile
for test in [
    'tests/test_v20_aitec_unit_solver.py',
    'tests/test_v20_aitec_terrain_tin.py',
    'tests/test_v20_aitec_building_solver.py',
    'tests/test_v20_aitec_basement_parking.py',
    'tests/test_v20_aitec_room_graph.py',
    'tests/test_v20_aitec_road_engineering.py',
    'tests/test_v20_aitec_environment.py',
    'tests/test_v20_aitec_finance.py',
]:
    subprocess.run(['python', test], check=True)
print('v20 A.I TEC advanced deterministic solver contracts OK')
