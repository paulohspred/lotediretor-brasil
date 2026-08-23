import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services'/'aitec-engine'/'app'))
from domain import validate_hard_constraints,rank_scenarios

class AitecV19ConstraintTests(unittest.TestCase):
    def test_all_hard_constraints_must_pass(self):
        r=validate_hard_constraints({'height_m':18,'spaces':24},[
            {'code':'height','metric':'height_m','operator':'<=','value':20},
            {'code':'parking','metric':'spaces','operator':'>=','value':20},
        ])
        self.assertEqual(r['status'],'PASS');self.assertEqual(r['passed'],2)
    def test_violation_fails(self):
        r=validate_hard_constraints({'height_m':21},[{'code':'height','metric':'height_m','operator':'<=','value':20}])
        self.assertEqual(r['status'],'FAIL');self.assertEqual(r['failed'],1)
    def test_missing_metric_never_passes(self):
        r=validate_hard_constraints({},[{'code':'height','metric':'height_m','operator':'<=','value':20}])
        self.assertEqual(r['status'],'UNVERIFIED');self.assertEqual(r['unevaluated'],1)
    def test_unverified_scenario_is_excluded_from_pareto(self):
        ranked=rank_scenarios([{'id':'valid','metrics':{'area':1}},{'id':'unknown','hard_invalid':True,'metrics':{'area':999}}],{'area':1})
        self.assertEqual([x['scenario_id'] for x in ranked],['valid'])
if __name__=='__main__':unittest.main()
