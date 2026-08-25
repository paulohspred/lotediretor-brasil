from __future__ import annotations

import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'services'/'solar-engine'))

from app import v20
from app.v20_api import REGISTRY, capabilities, execute_operation

source={
    'source_id':'src-dsm-1','kind':'DSM','captured_at':'2026-08-25T12:00:00Z','license_id':'TEST-LICENSE',
    'provenance_uri':'https://example.invalid/source','checksum_sha256':'a'*64,'crs':'EPSG:31983','resolution_m':1.0,
}
meta=v20.validate_source_snapshot(source)
assert meta['status']=='METADATA_COMPLETE'
assert meta['content_verified'] is False
assert len(meta['source_snapshot_id'])==64

samples=[
    {'x':0,'y':0,'z':10.0},{'x':1,'y':0,'z':10.1},{'x':0,'y':1,'z':10.0},{'x':1,'y':1,'z':10.1},
    {'x':2,'y':0,'z':12.0},{'x':2,'y':1,'z':12.1},
]
seg=v20.segment_roof_surfaces(samples,1.0,elevation_band_m=0.5,min_samples=2)
assert seg['status']=='PRELIMINARY_DSM_SEGMENTATION' and seg['surfaces']
obs=v20.detect_dsm_obstacles(samples,10.0,1.5,1.0,min_samples=1)
assert obs['status']=='PRELIMINARY_DSM_OBSTACLES' and obs['obstacles']

shadow1=v20.project_shadows([{'id':'chimney','x_m':2,'y_m':2,'width_m':1,'depth_m':1,'height_m':2}],180,45)
shadow2=v20.project_shadows([{'id':'chimney','x_m':2,'y_m':2,'width_m':1,'depth_m':1,'height_m':2}],180,45)
assert shadow1==shadow2 and shadow1['shadows'][0]['shadow_length_m']==2.0

missing_energy=v20.energy_from_irradiance(10,[100]*12,{'temperature':0.05})
assert missing_energy['status']=='REQUIRES_INPUT' and 'loss_fractions.inverter' in missing_energy['missing']
losses={name:0.02 for name in v20.LOSS_COMPONENTS}
energy=v20.energy_from_irradiance(10,[100]*12,losses)
assert energy['status']=='CALCULATED_FROM_EXPLICIT_IRRADIANCE_AND_LOSSES'
assert 0<energy['annual_net_kwh']<12000

battery=v20.simulate_battery([1,1,1,1],[2,0,2,0],2,1,1,0.9,0.1,0.5)
assert battery['status']=='CALCULATED_BATTERY_DISPATCH'
assert len(battery['soc_kwh'])==4 and min(battery['soc_kwh'])>=0.2-1e-9

balance={'grid_purchase_monthly_kwh':[100]*12,'injected_monthly_kwh':[20]*12}
tariff={
    'snapshot_id':'tariff-2026','effective_from':'2026-01-01','effective_to':'2026-12-31',
    'grid_purchase_rate_brl_per_kwh':1.0,'injection_credit_rate_brl_per_kwh':0.6,'minimum_bill_brl':25,
    'law_reference':'Lei 14.300 snapshot test','components':{'TE':'explicit','TUSD':'explicit','SCEE':'explicit','LAW_14300_RULESET':'explicit'},
    'source_snapshot_id':'src-tariff-1',
}
bill=v20.apply_tariff_snapshot(balance,tariff,'2026-08-25')
assert bill['status']=='CALCULATED_FROM_VERSIONED_TARIFF_SNAPSHOT' and bill['annual_bill_brl']==1056.0
assert v20.apply_tariff_snapshot(balance,tariff,'2027-01-01')['status']=='OUTSIDE_TARIFF_EFFECTIVE_PERIOD'

precheck=v20.connection_precheck({'requested_ac_kw':80,'requested_export_kw':70,'available_transformer_kw':100,'feeder_hosting_capacity_kw':60,'max_export_kw':50,'connection_voltage_v':380,'source_snapshot_id':'bdgd-1'})
assert precheck['status']=='PRECHECK_FAIL'
assert {c['code'] for c in precheck['checks'] if c['status']=='FAIL'}=={'FEEDER_HOSTING_CAPACITY','EXPORT_LIMIT'}

gm_missing=v20.ground_mount_layout({'site_width_m':100,'site_depth_m':60,'module_width_m':1.1,'module_length_m':2.2,'row_pitch_m':5,'modules_per_table':20,'tracker_mode':'SINGLE_AXIS','source_snapshot_id':'dem-1'})
assert gm_missing['status']=='REQUIRES_INPUT'
gm=v20.ground_mount_layout({'site_width_m':100,'site_depth_m':60,'module_width_m':1.1,'module_length_m':2.2,'row_pitch_m':5,'modules_per_table':20,'tracker_mode':'SINGLE_AXIS','tracker_rotation_limit_deg':60,'source_snapshot_id':'dem-1'})
assert gm['status']=='PRELIMINARY_GROUND_MOUNT_LAYOUT' and gm['panel_count']>0

safety=v20.safety_conditioning({'roof_load_capacity_kg_m2':25,'system_dead_load_kg_m2':15,'required_fire_setback_m':1.0,'provided_fire_setback_m':1.2,'structural_review_status':'PENDING','fire_review_status':'REVIEWED'})
assert safety['status']=='REQUIRES_PROFESSIONAL_REVIEW'

cal=v20.calibration_compare([100,110,90],[100,110,90],'real-system-1')
assert cal['rmse_kwh']==0 and cal['mape']==0

ocr_source={**source,'source_id':'bill-ocr-1','kind':'BILL_OCR'}
ocr=v20.parse_bill_ocr_text('Consumo 456 kWh Total R$ 321,45',ocr_source)
assert ocr['status']=='REQUIRES_REVIEW' and 456 in ocr['consumption_candidates_kwh'] and 321.45 in ocr['currency_candidates_brl']

equipment={'equipment_type':'MODULE','manufacturer':'Example','model':'X550','datasheet_uri':'https://example.invalid/x.pdf','datasheet_sha256':'b'*64,'source_uri':'https://example.invalid/catalog','captured_at':'2026-08-25'}
e1=v20.equipment_snapshot(equipment);e2=v20.equipment_snapshot(dict(equipment))
assert e1['equipment_snapshot_id']==e2['equipment_snapshot_id'] and e1['commercial_availability_verified'] is False

scene=v20.build_scene_3d(seg['surfaces'],obs['obstacles'],[{'id':'P-1','geometry':{'type':'Polygon','coordinates':[]}}],[meta['source_snapshot_id']])
assert scene['status']=='SCENE_MODEL_READY' and scene['renderer_contract']['threejs'] is True and scene['renderer_contract']['cesium'] is True

report=v20.build_scenario_report('solar-case-1','2026-08-25',[source],{'dc_kwp':10},{'annual_net_kwh':energy['annual_net_kwh']},{'overall':'MEDIUM'},{'annual_energy_pct':10})
assert report['status']=='REPORT_READY' and report['classification']=='PRELIMINARY_ENGINEERING_STUDY'
assert report['sources'][0]['source_snapshot_id']==meta['source_snapshot_id']
assert report['external_gates']

required={'source.validate','dsm.roof-surfaces','dsm.obstacles','shadow.project','energy.irradiance','battery.simulate','tariff.apply','connection.precheck','ground-mount.layout','safety.conditioning','calibration.compare','bill.parse-ocr','equipment.snapshot','scene.build','report.build'}
assert required==set(REGISTRY)
assert len(capabilities())==len(required)
api_energy=execute_operation('energy.irradiance',kwargs={'dc_kwp':5,'monthly_poa_kwh_m2':[100]*12,'loss_fractions':losses})
assert api_energy['status']=='CALCULATED_FROM_EXPLICIT_IRRADIANCE_AND_LOSSES'
try:execute_operation('invent.default')
except ValueError as exc:assert 'unknown Solar v20 operation' in str(exc)
else:raise AssertionError('unknown operations must be rejected')

assert 'app.entrypoint:app' in (root/'services'/'solar-engine'/'Dockerfile').read_text()
assert 'Depends(internal_token)' in (root/'services'/'solar-engine'/'app'/'entrypoint.py').read_text()
print('v20 Solar reproducible scenario engine gate OK')
