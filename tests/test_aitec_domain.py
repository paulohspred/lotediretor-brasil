import sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services'/'aitec-engine'/'app'))
from domain import parking_area, massing_capacity, rank_scenarios

class AitecDomainTests(unittest.TestCase):
    def test_parking(self):
        r=parking_area(10,2.5,5,1.6)
        self.assertAlmostEqual(r['estimated_total_area_m2'],200.0)
    def test_massing_uses_more_restrictive_limit(self):
        r=massing_capacity(parcel_area_m2=1000,buildable_area_m2=400,ca_max=2,height_max_m=9,floor_height_m=3,efficiency=.8)
        self.assertEqual(r['estimated_floor_count'],3)
        self.assertAlmostEqual(r['max_gross_floor_area_m2'],1200)
        self.assertAlmostEqual(r['estimated_net_area_m2'],960)
    def test_rank_drops_hard_invalid(self):
        ranked=rank_scenarios([
            {'id':'a','metrics':{'area':100}},
            {'id':'b','metrics':{'area':200}},
            {'id':'bad','hard_invalid':True,'metrics':{'area':999}},
        ],{'area':1})
        self.assertEqual([x['scenario_id'] for x in ranked],['b','a'])

if __name__=='__main__': unittest.main()
