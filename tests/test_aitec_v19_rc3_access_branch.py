from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services'/'aitec-engine'))
from shapely.geometry import box,Point
from app.domain import generate_access_road_layout,generate_site_solutions

def main():
    parcel=box(0,0,120,90);building=box(50,30,75,60);aisle=box(20,20,28,70)
    road=generate_access_road_layout(parcel,[building],[aisle],Point(0,45),6)
    assert road['status']=='PASS',road
    assert road['connected'] and parcel.covers(road['road'])
    assert road['road'].intersection(building).area<1e-7

    locked=box(20,20,35,35)
    items=generate_site_solutions(box(0,0,100,80),8000,2.0,.55,.10,36,
        min_buildings=2,max_buildings=3,min_spacing_m=5,required_spaces=20,count=12,seed=1903,
        parcel_geometry=box(0,0,100,80),access_point=Point(0,40),access_required=True,road_width_m=6,
        unit_mix=[{'name':'2D','target_area_m2':65,'min_count':4,'target_share':.7},{'name':'3D','target_area_m2':85,'min_count':2,'target_share':.3}],
        min_total_units=6,locked_footprints=[locked])
    assert items, 'expected branch candidates'
    for item in items:
        assert item['locked_count']==1
        assert item['footprints'][0].equals_exact(locked,1e-9), 'locked footprint changed'
    valid=[x for x in items if not x['hard_invalid']]
    assert valid, [(x['validation']['status'],x['metrics']) for x in items]
    assert any(x['road']['status']=='PASS' for x in valid)
    assert all(x['metrics']['access_connected']==1 for x in valid)

    api=(ROOT/'services/platform-api/src/v7.controller.ts').read_text()
    for needle in ("aitec/solutions/:solutionId/locks","aitec/solutions/:solutionId/branch",'locked_footprints','parent_solution_id'):
        assert needle in api,needle
    migration=(ROOT/'db/platform/migrations/195_v19_rc3_aitec_deepening.sql').read_text()
    assert 'aitec_solution_project_tenant_fk' in migration
    print(f'v19-rc3 access/lock/branch OK ({len(valid)}/{len(items)} hard-valid)')

if __name__=='__main__':main()
