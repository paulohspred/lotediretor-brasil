from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
paths={'unit':'unit_solver.py','terrain':'terrain_solver.py','building':'building_solver.py','basement':'basement_parking_solver.py','room':'room_solver.py','road':'road_engineering_solver.py','environment':'environment_solver.py'}
files={name:(root/'services/aitec-engine/app'/path).read_text() for name,path in paths.items()}
checks={
'unit':["DESIGN_DNA_VERSION = 'aitec-design-dna-v20.1'",'solve_unit_distribution','compare_designs'],
'terrain':["TERRAIN_SOLVER_VERSION = 'aitec-terrain-v20.1'",'build_tin','contour_segments','plateau_candidates','cut_fill_against_pad'],
'building':["BUILDING_SOLVER_VERSION = 'aitec-building-v20.1'",'solve_building_system','CORE_FIT:','VERTICAL_COMPONENTS_FIT:'],
'basement':["BASEMENT_PARKING_VERSION = 'aitec-basement-parking-v20.1'",'solve_basement_parking','RAMP_MAX_SLOPE','PARKING_TOTAL_MIN','PARKING_ACCESSIBLE_MIN','PARKING_EV_MIN'],
'room':["ROOM_SOLVER_VERSION = 'aitec-room-graph-v20.1'",'solve_unit_room_graph','ADJACENCY:','INTERNAL_OPENING:','EXTERIOR_OPENING:'],
'road':["ROAD_SOLVER_VERSION = 'aitec-road-engineering-v20.1'",'evaluate_road_engineering','ROAD_MIN_TURN_RADIUS','ROAD_MAX_GRADE','EMERGENCY_MIN_WIDTH'],
'environment':["ENVIRONMENT_SOLVER_VERSION = 'aitec-environment-v20.1'",'analyze_solar_exposure','analyze_daylight','analyze_noise','analyze_wind','analyze_environment','SOLAR_EXPOSURE_MIN','DAYLIGHT_PROXY_MIN','NOISE_MAX_DB','WIND_COMFORT_MAX_SPEED',"status = 'UNVERIFIED'"]}
for name,tokens in checks.items():
    for token in tokens:assert token in files[name],token
for name,tokens in {'basement':['does not infer local parking'],'room':['does not infer local','não inventa norma local'],'road':['does not infer local','nenhuma norma local é inferida'],'environment':['not irradiance or energy yield','não substitui CFD','UNVERIFIED']}.items():
    for token in tokens:assert token in files[name],token
assert 'COPY services/aitec-engine/app ./app' in (root/'services/aitec-engine/Dockerfile').read_text()
for test in ['tests/test_v20_aitec_unit_solver.py','tests/test_v20_aitec_terrain_tin.py','tests/test_v20_aitec_building_solver.py','tests/test_v20_aitec_basement_parking.py','tests/test_v20_aitec_room_graph.py','tests/test_v20_aitec_road_engineering.py','tests/test_v20_aitec_environment.py']:subprocess.run(['python',test],check=True)
print('v20 A.I TEC environment contracts OK')
