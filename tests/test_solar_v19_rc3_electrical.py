from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services'/'solar-engine'))
from app.domain import electrical_string_design

def main():
    missing=electrical_string_design(36,{'watts':550},{'ac_kw':15},-5,70)
    assert missing['status']=='REQUIRES_INPUT' and missing['missing']
    module={'watts':550,'voc_v':49.8,'vmp_v':41.8,'isc_a':14.0,'imp_a':13.2,'temp_coeff_voc_pct_per_c':-0.25,'temp_coeff_vmp_pct_per_c':-0.30}
    inverter={'ac_kw':15,'max_dc_kw':22.5,'mppt_count':3,'mppt_min_v':180,'mppt_max_v':850,'max_dc_v':1000,'max_input_current_a_per_mppt':30}
    out=electrical_string_design(36,module,inverter,-5,70)
    assert out['status']=='PRELIMINARY_VALIDATED_DATASHEET',out
    assert sum(x['modules'] for x in out['strings'])==36
    assert out['dc_kwp']==19.8
    assert all(x['status']=='PASS' for x in out['checks'])
    for st in out['strings']:
        assert st['voc_cold_v']<=inverter['max_dc_v']
        assert st['vmp_hot_v']>=inverter['mppt_min_v']
        assert st['vmp_cold_v']<=inverter['mppt_max_v']
    engine=(ROOT/'services/solar-engine/app/main.py').read_text();api=(ROOT/'services/platform-api/src/solar/solar.controller.ts').read_text();mig=(ROOT/'db/platform/migrations/196_v19_rc3_solar_electrical.sql').read_text()
    assert '/solar/v1/electrical-string-design' in engine
    assert "projects/:id/electrical-design" in api
    assert 'solar.electrical_design' in mig and 'solar_regulation_global_code_date_uidx' in mig
    print('v19-rc3 solar electrical design OK')

if __name__=='__main__':main()
