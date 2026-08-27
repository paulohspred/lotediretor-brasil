from __future__ import annotations

import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'services'/'solar-engine'))

from app import v20_advanced
from app.v20_api import REGISTRY, execute_operation

# Solar position is deterministic and requires an explicit UTC offset.
pos1=v20_advanced.solar_position(-23.5505,-46.6333,'2026-12-21T12:00:00-03:00')
pos2=v20_advanced.solar_position(-23.5505,-46.6333,'2026-12-21T12:00:00-03:00')
assert pos1==pos2
assert pos1['status']=='CALCULATED_SOLAR_POSITION_APPROXIMATE'
assert pos1['elevation_deg']>80
assert 0<=pos1['azimuth_deg']<360
assert v20_advanced.solar_position(-23.55,-46.63,'2026-12-21T12:00:00')['status']=='REQUIRES_INPUT'

poa=v20_advanced.plane_of_array_irradiance(850,700,150,30,0,20,0,0.2)
assert poa['status']=='CALCULATED_ISOTROPIC_POA'
assert poa['poa_global_w_m2']>0
assert abs(poa['poa_global_w_m2']-(poa['poa_beam_w_m2']+poa['poa_sky_diffuse_w_m2']+poa['poa_ground_diffuse_w_m2']))<1e-4

layout=v20_advanced.roof_rect_layout(10,6,1.1,2.2,0.5,0.1,0.1,'PORTRAIT',[])
assert layout['status']=='PRELIMINARY_ROOF_LAYOUT' and layout['panel_count']>0
blocked=v20_advanced.roof_rect_layout(10,6,1.1,2.2,0.5,0.1,0.1,'PORTRAIT',[{'x_m':3,'y_m':0.5,'width_m':3,'depth_m':5}])
assert 0<blocked['panel_count']<layout['panel_count']

module={'pmax_w':550,'voc_stc_v':49.5,'vmp_stc_v':41.5,'isc_stc_a':13.9,'imp_stc_a':13.2,'voc_temp_coeff_pct_per_c':-0.28,'vmp_temp_coeff_pct_per_c':-0.35}
inverter={'max_dc_voltage_v':1100,'mppt_min_v':200,'mppt_max_v':1000,'max_input_current_a_per_mppt':32,'mppt_count':6,'max_ac_power_kw':50}
electrical=v20_advanced.string_mppt_design(module,inverter,100,0,70)
assert electrical['status']=='ELECTRICAL_DESIGN_OK'
assert electrical['used_module_count']==100 and electrical['unallocated_module_count']==0
assert electrical['modules_per_string']>=electrical['series_range']['min']
assert electrical['modules_per_string']<=electrical['series_range']['max']
assert sum(electrical['strings_per_mppt'])==electrical['string_count']
assert electrical['temperature_adjusted']['string_voc_cold_v']<=inverter['max_dc_voltage_v']
assert electrical['dc_ac_ratio']>0

financial=v20_advanced.financial_projection(
    100000,20000,1.0,25,0.08,0.005,0.04,1000,0.04,
    [{'year':12,'cost_brl':10000}],
)
assert financial['status']=='CALCULATED_EXPLICIT_FINANCIAL_PROJECTION'
assert len(financial['cashflows'])==25
assert financial['npv_brl']>0
assert financial['irr'] is not None and financial['irr']>0
assert financial['simple_payback_year'] is not None
assert financial['assumptions']['replacements'][0]['year']==12

required={'solar.position','irradiance.poa','roof.layout','electrical.string-mppt','financial.project'}
assert required.issubset(REGISTRY)
api_pos=execute_operation('solar.position',kwargs={'latitude_deg':-23.5505,'longitude_deg':-46.6333,'timestamp_iso':'2026-12-21T12:00:00-03:00'})
assert api_pos['status']=='CALCULATED_SOLAR_POSITION_APPROXIMATE'
print('v20 Solar advanced geometry/electrical/financial gate OK')
