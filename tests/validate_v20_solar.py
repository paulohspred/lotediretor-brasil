from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
domain=(root/'services/solar-engine/app/v20.py').read_text()
advanced=(root/'services/solar-engine/app/v20_advanced.py').read_text()
api=(root/'services/solar-engine/app/v20_api.py').read_text()
entrypoint=(root/'services/solar-engine/app/entrypoint.py').read_text()
dockerfile=(root/'services/solar-engine/Dockerfile').read_text()

for token in [
    "SOLAR_V20_VERSION = 'solar-scenario-v20.1'",'validate_source_snapshot','segment_roof_surfaces','detect_dsm_obstacles',
    'project_shadows','energy_from_irradiance','simulate_battery','apply_tariff_snapshot','connection_precheck',
    'ground_mount_layout','safety_conditioning','calibration_compare','parse_bill_ocr_text','equipment_snapshot','build_scene_3d','build_scenario_report',
    "'status':'REQUIRES_INPUT'",'commercial_availability_verified',
]:
    assert token in domain,token
for token in [
    'solar_position','plane_of_array_irradiance','roof_rect_layout','string_mppt_design','financial_projection',
    'CALCULATED_SOLAR_POSITION_APPROXIMATE','CALCULATED_ISOTROPIC_POA','PRELIMINARY_ROOF_LAYOUT',
    'ELECTRICAL_DESIGN_OK','CALCULATED_EXPLICIT_FINANCIAL_PROJECTION','clipping_simulation_required',
]:
    assert token in advanced,token
for token in ['REGISTRY','solar.position','irradiance.poa','roof.layout','electrical.string-mppt','financial.project','energy.irradiance','battery.simulate','tariff.apply','scene.build','report.build','unknown Solar v20 operation']:
    assert token in api,token
assert 'Depends(internal_token)' in entrypoint
assert 'include_router(solar_v20_router' in entrypoint
assert 'app.entrypoint:app' in dockerfile
subprocess.run(['python','tests/test_v20_solar_scenario.py'],check=True)
subprocess.run(['python','tests/test_v20_solar_advanced.py'],check=True)
print('v20 Solar 360 reproducible scenario implementation gate OK')
