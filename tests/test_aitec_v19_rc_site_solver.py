from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services'/'aitec-engine'))

from shapely.geometry import box
from app.domain import generate_site_solutions, pareto_frontier


def signature(items):
    return [
        (
            x['variation'],
            x['metrics']['building_count'],
            x['metrics']['gross_floor_area_m2'],
            x['metrics']['total_units'],
            tuple(round(g.area,4) for g in x['footprints']),
        )
        for x in items
    ]


def validate_geometry(items,envelope):
    for item in items:
        footprints=item['footprints']
        assert footprints, item
        for fp in footprints:
            assert envelope.covers(fp), 'generated footprint must stay inside legal envelope'
        for i,a in enumerate(footprints):
            for b in footprints[i+1:]:
                assert not a.intersects(b), 'building footprints may not overlap'
        assert item['validation']['status']=='PASS', item['validation']
        assert not item['hard_invalid']
        m=item['metrics']
        assert m['ca_used'] <= 2.0 + 1e-6
        assert m['to_used'] <= 0.60 + 1e-6
        assert m['tp_achieved'] >= 0.10 - 1e-6
        assert m['height_m'] <= 36.0 + 1e-6


def main():
    envelope=box(0,0,100,80)
    a=generate_site_solutions(envelope,8000,2.0,.60,.10,36,count=30,seed=1901,required_spaces=10,min_spacing_m=6)
    b=generate_site_solutions(envelope,8000,2.0,.60,.10,36,count=30,seed=1901,required_spaces=10,min_spacing_m=6)
    assert len(a)>=20, f'expected many diverse alternatives, got {len(a)}'
    assert signature(a)==signature(b), 'same snapshot/seed must reproduce the same alternatives'
    validate_geometry(a,envelope)
    # Diversity guard: different generated alternatives cannot collapse to clones.
    unique={(x['metrics']['building_count'],x['metrics']['footprint_area_m2'],x['angle_deg']) for x in a}
    assert len(unique)>=max(10,len(a)//2), (len(unique),len(a))
    frontier=pareto_frontier(a,{'estimated_net_area_m2':'MAX','tp_achieved':'MAX','parking_area_m2':'MIN'})
    assert frontier and all(not x['hard_invalid'] for x in frontier)
    # Persistence/API contracts must exist and preserve geometry/violations separately.
    sql=(ROOT/'db/platform/migrations/194_v19_rc_aitec_site_solver.sql').read_text()
    for needle in ('aitec.solution','aitec.geometry_object','aitec.violation','aitec.solution_lock','FORCE ROW LEVEL SECURITY'):
        assert needle in sql, needle
    api=(ROOT/'services/platform-api/src/v7.controller.ts').read_text()
    for needle in ("aitec/projects/:id/solutions/generate","/aitec/v1/site-solver","aitec.geometry_object","aitec.violation","aitec.solutions.generated"):
        assert needle in api, needle
    print(f'v19-rc A.I TEC site solver OK ({len(a)} alternatives, Pareto {len(frontier)})')


if __name__=='__main__':
    main()
