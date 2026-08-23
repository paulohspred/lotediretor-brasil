from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services'/'aitec-engine'))
from shapely.geometry import box
from app.domain import allocate_unit_mix,estimate_cut_fill_from_samples,solve_building_stack

def main():
    mix=allocate_unit_mix(2500,[{'name':'2D','target_area_m2':65,'min_count':8,'target_share':.55},{'name':'3D','target_area_m2':85,'min_count':4,'target_share':.30},{'name':'1D','target_area_m2':45,'min_count':2,'target_share':.15}],14)
    assert mix['status']=='PASS',mix
    assert mix['total_units']>=14
    assert all(x['count']>=x['min_count'] for x in mix['items'])
    impossible=allocate_unit_mix(100,[{'name':'3D','target_area_m2':85,'min_count':2}],2)
    assert impossible['status']=='SHORTFALL'

    fp=box(0,0,20,20)
    flat=[{'x':2,'y':2,'z':100},{'x':18,'y':2,'z':100},{'x':2,'y':18,'z':100},{'x':18,'y':18,'z':100}]
    earth=estimate_cut_fill_from_samples([fp],flat)
    assert earth['status']=='CALCULATED_PRELIMINARY'
    assert earth['earthwork_m3']==0
    slope=[{'x':2,'y':2,'z':98},{'x':18,'y':2,'z':99},{'x':2,'y':18,'z':101},{'x':18,'y':18,'z':102}]
    earth2=estimate_cut_fill_from_samples([fp],slope)
    assert earth2['earthwork_m3']>0

    b=solve_building_stack([fp],6,40,1.8)
    assert b['status']=='PRELIMINARY',b
    assert len(b['cores'])==1 and fp.covers(b['cores'][0])
    assert b['buildings'][0]['floors']==6
    assert b['total_net_program_area_m2']>0

    main_py=(ROOT/'services/aitec-engine/app/main.py').read_text()
    for needle in ("/aitec/v1/unit-mix","/aitec/v1/cut-fill","/aitec/v1/building-solver",'BUILDING_CORE','CIRCULATION_ZONE'):
        assert needle in main_py,needle
    print('v19-rc3 program/terrain/building solver OK')

if __name__=='__main__':main()
