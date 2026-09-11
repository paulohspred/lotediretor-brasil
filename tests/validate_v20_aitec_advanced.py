from pathlib import Path
import re
import subprocess

root=Path(__file__).resolve().parents[1]
paths={'unit':'unit_solver.py','terrain':'terrain_solver.py','building':'building_solver.py','basement':'basement_parking_solver.py','room':'room_solver.py','road':'road_engineering_solver.py','environment':'environment_solver.py','finance':'finance_solver.py','export':'export_solver.py','ingest':'ingest_solver.py','optimization':'optimization_solver.py'}
files={name:(root/'services/aitec-engine/app'/path).read_text() for name,path in paths.items()}
required={
'unit':["DESIGN_DNA_VERSION = 'aitec-design-dna-v20.1'",'solve_unit_distribution','compare_designs'],
'terrain':["TERRAIN_SOLVER_VERSION = 'aitec-terrain-v20.1'",'build_tin','contour_segments','plateau_candidates','cut_fill_against_pad'],
'building':["BUILDING_SOLVER_VERSION = 'aitec-building-v20.1'",'solve_building_system'],
'basement':["BASEMENT_PARKING_VERSION = 'aitec-basement-parking-v20.1'",'solve_basement_parking','RAMP_MAX_SLOPE'],
'room':["ROOM_SOLVER_VERSION = 'aitec-room-graph-v20.1'",'solve_unit_room_graph','ADJACENCY:','INTERNAL_OPENING:'],
'road':["ROAD_SOLVER_VERSION = 'aitec-road-engineering-v20.1'",'evaluate_road_engineering','ROAD_MIN_TURN_RADIUS','ROAD_MAX_GRADE'],
'environment':["ENVIRONMENT_SOLVER_VERSION = 'aitec-environment-v20.1'",'analyze_environment','SOLAR_EXPOSURE_MIN','DAYLIGHT_PROXY_MIN','NOISE_MAX_DB','WIND_COMFORT_MAX_SPEED'],
'finance':["FINANCE_SOLVER_VERSION = 'aitec-finance-v20.1'",'calculate_project_finance','market_snapshot_id','cost_snapshot_id','pareto_metrics'],
'export':["EXPORT_VERSION = 'aitec-export-v20.1'",'export_geojson','export_kmz','export_dxf','export_ifc','export_xlsx','export_pdf','export_gltf','export_manifest'],
'ingest':["INGEST_VERSION = 'aitec-ingest-v20.1'",'ingest_dataset','ingest_shapefile','ingest_gpkg','ingest_dxf','ingest_ifc','missing CRS is never guessed'],
'optimization':["OPTIMIZATION_VERSION='aitec-optimization-v20.1'",'explain_pareto','visual_geometry_diff','dominated_by','balanced_score','symmetric_difference','fingerprint']}
for name,tokens in required.items():
    for token in tokens:assert token in files[name],token

api=(root/'services/aitec-engine/app/advanced_api.py').read_text()
entrypoint=(root/'services/aitec-engine/app/entrypoint.py').read_text()
dockerfile=(root/'services/aitec-engine/Dockerfile').read_text()
for token in ['OP_REGISTRY','STUDY_PREPROJECT_NOT_EXECUTIVE','terrain.tin','optimization.pareto','ingest.dataset','export.ifc','serialize_result']:
    assert token in api,token
assert 'Depends(internal_token)' in entrypoint
assert 'include_router(advanced_router' in entrypoint
# Validate the image contract rather than one exact COPY spelling. Security hardening may
# legitimately add --chown while preserving the same application source/destination.
assert re.search(r'^COPY(?:\s+--\S+(?:=\S+)?)?\s+services/aitec-engine/app\s+\./app\s*$',dockerfile,re.M), 'aitec app COPY missing'
assert re.search(r'^USER\s+(?!root\b)\S+',dockerfile,re.M), 'aitec runtime must be non-root'
assert 'app.entrypoint:app' in dockerfile

for test in [
    'tests/test_v20_aitec_unit_solver.py','tests/test_v20_aitec_terrain_tin.py','tests/test_v20_aitec_building_solver.py',
    'tests/test_v20_aitec_basement_parking.py','tests/test_v20_aitec_room_graph.py','tests/test_v20_aitec_road_engineering.py',
    'tests/test_v20_aitec_environment.py','tests/test_v20_aitec_finance.py','tests/test_v20_aitec_exports.py',
    'tests/test_v20_aitec_ingest.py','tests/test_v20_aitec_optimization.py','tests/test_v20_aitec_runtime_api.py'
]:
    subprocess.run(['python',test],check=True)
print('v20 A.I TEC full advanced implementation + runtime API gate OK')
