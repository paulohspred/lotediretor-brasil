from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
unit=(root/'services/aitec-engine/app/unit_solver.py').read_text();terrain=(root/'services/aitec-engine/app/terrain_solver.py').read_text();building=(root/'services/aitec-engine/app/building_solver.py').read_text();basement=(root/'services/aitec-engine/app/basement_parking_solver.py').read_text();room=(root/'services/aitec-engine/app/room_solver.py').read_text();docker=(root/'services/aitec-engine/Dockerfile').read_text()
checks=[
(unit,["DESIGN_DNA_VERSION = 'aitec-design-dna-v20.1'",'solve_unit_distribution','compare_designs','PROGRAM_MIN_UNITS','UNIT_MIN:','UNIT_MAX:']),
(terrain,["TERRAIN_SOLVER_VERSION = 'aitec-terrain-v20.1'",'build_tin','contour_segments','plateau_candidates','cut_fill_against_pad','slope_percent','aspect_deg']),
(building,["BUILDING_SOLVER_VERSION = 'aitec-building-v20.1'",'solve_building_system','CORE_FIT:','VERTICAL_COMPONENTS_FIT:']),
(basement,["BASEMENT_PARKING_VERSION = 'aitec-basement-parking-v20.1'",'solve_basement_parking','RAMP_REQUIRED','RAMP_MAX_SLOPE','PARKING_TOTAL_MIN','PARKING_ACCESSIBLE_MIN','PARKING_EV_MIN']),
(room,["ROOM_SOLVER_VERSION = 'aitec-room-graph-v20.1'",'solve_unit_room_graph','ROOM_MIN_AREA:','ROOM_MIN_WIDTH:','ROOM_MIN_DEPTH:','ADJACENCY:','INTERNAL_OPENING:','EXTERIOR_OPENING:','ROOMS_NO_OVERLAP','ROOMS_COVER_UNIT'])]
for source,tokens in checks:
    for token in tokens:assert token in source,token
for source,tokens in [(unit,['não gera planta arquitetônica','Não inventa fachada']),(terrain,['não inventa DEM/topografia','Não substitui levantamento topográfico']),(building,['não inventa requisitos normativos','Não substitui projeto arquitetônico']),(basement,['does not infer local parking','não constituem projeto estrutural']),(room,['does not infer local','não é projeto executivo','não inventa norma local'])]:
    for token in tokens:assert token in source,token
assert 'COPY services/aitec-engine/app ./app' in docker
for test in ['tests/test_v20_aitec_unit_solver.py','tests/test_v20_aitec_terrain_tin.py','tests/test_v20_aitec_building_solver.py','tests/test_v20_aitec_basement_parking.py','tests/test_v20_aitec_room_graph.py']:subprocess.run(['python',test],check=True)
print('v20 A.I TEC room graph contracts OK')
