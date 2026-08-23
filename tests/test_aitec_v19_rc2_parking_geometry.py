from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services'/'aitec-engine'))

from shapely.geometry import box
from app.domain import generate_surface_parking_layout,generate_site_solutions


def main():
    legal=box(0,0,100,80)
    building=box(35,25,65,55)
    layout=generate_surface_parking_layout(legal,[building],40,2.5,5.0,6.0,1.0)
    assert layout['status']=='PASS', layout
    assert layout['generated_spaces']==40
    assert layout['shortfall']==0
    assert len(layout['stalls'])==40
    assert layout['aisles']
    exclusion=building.buffer(1.0,join_style=2)
    for stall in layout['stalls']:
        assert legal.covers(stall)
        assert stall.intersection(exclusion).area < 1e-8
    for i,a in enumerate(layout['stalls']):
        for b in layout['stalls'][i+1:]:
            assert a.intersection(b).area < 1e-8, 'parking stalls may not overlap'
    for aisle in layout['aisles']:
        assert legal.covers(aisle)
        assert aisle.intersection(exclusion).area < 1e-8

    # A deliberately impossible target must become a hard-invalid scenario,
    # never a silently accepted surface-parking estimate.
    impossible=generate_surface_parking_layout(box(0,0,30,20),[box(8,5,22,15)],100)
    assert impossible['status']=='SHORTFALL'
    assert impossible['shortfall']>0

    items=generate_site_solutions(legal,8000,2.0,.60,.10,36,count=20,seed=1902,required_spaces=40,min_spacing_m=6)
    assert len(items)>=15
    valid=[x for x in items if not x['hard_invalid']]
    assert valid
    for item in valid:
        m=item['metrics']
        assert m['parking_spaces_generated']>=m['required_spaces']
        assert m['parking_shortfall']==0
        assert item['validation']['status']=='PASS'
        checks={x['code']:x for x in item['validation']['results']}
        assert checks['PARKING_MIN']['status']=='PASS'
        assert len(item['parking_stalls'])==m['required_spaces']
        assert item['parking_aisles']

    main_py=(ROOT/'services/aitec-engine/app/main.py').read_text()
    for needle in ('PARKING_STALL','DRIVE_AISLE','site-solver-rc3','stall_width_m','aisle_width_m'):
        assert needle in main_py, needle
    api=(ROOT/'services/platform-api/src/v7.controller.ts').read_text()
    for needle in ('stall_width_m','stall_length_m','aisle_width_m','site-solver-rc3'):
        assert needle in api, needle
    print(f'v19-rc2 A.I TEC parking geometry OK ({len(valid)}/{len(items)} hard-valid alternatives)')


if __name__=='__main__':
    main()
