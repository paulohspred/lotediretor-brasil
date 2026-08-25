from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
files={name:(root/path).read_text() for name,path in {
'unit':'services/aitec-engine/app/unit_solver.py','terrain':'services/aitec-engine/app/terrain_solver.py','building':'services/aitec-engine/app/building_solver.py','basement':'services/aitec-engine/app/basement_parking_solver.py','room':'services/aitec-engine/app/room_solver.py','road':'services/aitec-engine/app/road_engineering_solver.py'}.items()}
checks={
'unit':["DESIGN_DNA_VERSION = 'aitec-design-dna-v20.1'",'solve_unit_distribution','compare_designs','PROGRAM_MIN_UNITS'],
'terrain':["TERRAIN_SOLVER_VERSION = 'aitec-terrain-v20.1'",'build_tin','contour_segments','plateau_candidates','cut_fill_against_pad'],
'building':["BUILDING_SOLVER_VERSION = 'aitec-building-v20.1'",'solve_building_system','CORE_FIT:','VERTICAL_COMPONENTS_FIT:'],
'basement':["BASEMENT_PARKING_VERSION = 'aitec-basement-parking-v20.1'",'solve_basement_parking','RAMP_MAX_SLOPE','PARKING_TOTAL_MIN','PARKING_ACCESSIBLE_MIN','PARKING_EV_MIN'],
'room':["ROOM_SOLVER_VERSION = 'aitec-room-graph-v20.1'",'solve_unit_room_graph','ADJACENCY:','INTERNAL_OPENING:','EXTERIOR_OPENING:','ROOMS_NO_OVERLAP'],
'road':["ROAD_SOLVER_VERSION = 'aitec-road-engineering-v20.1'",'evaluate_road_engineering','ROAD_SURFACE_INSIDE_PARCEL','ACCESS_AT_BOUNDARY','ROAD_MIN_TURN_RADIUS','ROAD_GRADE_DATA','ROAD_MAX_GRADE','EMERGENCY_MIN_WIDTH']}
for name,tokens in checks.items():
    for token in tokens:assert token in files[name],token
for name,tokens in {'basement':['does not infer local parking','não constituem projeto estrutural'],'room':['does not infer local','não inventa norma local'],'road':['does not infer local','não gera projeto viário executivo','nenhuma norma local é inferida']}.items():
    for token in tokens:assert token in files[name],token
assert 'COPY services/aitec-engine/app ./app' in (root/'services/aitec-engine/Dockerfile').read_text()
for test in ['tests/test_v20_aitec_unit_solver.py','tests/test_v20_aitec_terrain_tin.py','tests/test_v20_aitec_building_solver.py','tests/test_v20_aitec_basement_parking.py','tests/test_v20_aitec_room_graph.py','tests/test_v20_aitec_road_engineering.py']:subprocess.run(['python',test],check=True)
print('v20 A.I TEC road engineering contracts OK')
