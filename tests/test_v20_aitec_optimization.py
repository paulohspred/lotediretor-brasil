from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'services'/'aitec-engine'/'app'))
from optimization_solver import OPTIMIZATION_VERSION,explain_pareto,visual_geometry_diff  # noqa:E402

class OptimizationV20Tests(unittest.TestCase):
    def test_pareto_explains_frontier_dominance_and_exclusions(self):
        result=explain_pareto([
            {'id':'A','metrics':{'profit':100,'cost':80,'daylight':0.2}},
            {'id':'B','metrics':{'profit':120,'cost':90,'daylight':0.25}},
            {'id':'C','metrics':{'profit':90,'cost':100,'daylight':0.1}},
            {'id':'D','hard_invalid':True,'metrics':{'profit':999,'cost':1,'daylight':1}},
            {'id':'E','metrics':{'profit':110,'cost':None,'daylight':0.3}},
        ],{'profit':'MAX','cost':'MIN','daylight':'MAX'})
        self.assertEqual(result['version'],OPTIMIZATION_VERSION)
        frontier={x['id'] for x in result['frontier']};self.assertIn('A',frontier);self.assertIn('B',frontier);self.assertNotIn('C',frontier)
        c=next(x for x in result['dominated'] if x['id']=='C');self.assertTrue(c['dominated_by'])
        self.assertEqual({x['id'] for x in result['excluded']},{'D','E'})
        self.assertTrue(all(0<=v<=1 for item in result['frontier']+result['dominated'] for v in item['normalized_objectives'].values()))

    def test_visual_diff_reports_added_removed_changed_and_unchanged(self):
        before={'type':'FeatureCollection','features':[
            {'type':'Feature','properties':{'id':'same'},'geometry':{'type':'Polygon','coordinates':[[[0,0],[2,0],[2,2],[0,2],[0,0]]]}},
            {'type':'Feature','properties':{'id':'move'},'geometry':{'type':'Polygon','coordinates':[[[3,0],[5,0],[5,2],[3,2],[3,0]]]}},
            {'type':'Feature','properties':{'id':'old'},'geometry':{'type':'Polygon','coordinates':[[[6,0],[7,0],[7,1],[6,1],[6,0]]]}}]}
        after={'type':'FeatureCollection','features':[
            {'type':'Feature','properties':{'id':'same'},'geometry':before['features'][0]['geometry']},
            {'type':'Feature','properties':{'id':'move'},'geometry':{'type':'Polygon','coordinates':[[[4,0],[6,0],[6,2],[4,2],[4,0]]]}},
            {'type':'Feature','properties':{'id':'new'},'geometry':{'type':'Polygon','coordinates':[[[8,0],[9,0],[9,1],[8,1],[8,0]]]}}]}
        result=visual_geometry_diff(before,after);kinds={x['id']:x['change'] for x in result['summary']}
        self.assertEqual(kinds,{'move':'CHANGED','new':'ADDED','old':'REMOVED','same':'UNCHANGED'});self.assertEqual(len(result['fingerprint']),64);self.assertEqual(len(result['diff']['features']),3)

    def test_missing_objective_never_enters_frontier(self):
        result=explain_pareto([{'id':'A','metrics':{'x':1}},{'id':'B','metrics':{}}],{'x':'MAX'})
        self.assertEqual([x['id'] for x in result['frontier']],['A']);self.assertEqual(result['excluded'][0]['id'],'B')

    def test_duplicate_visual_keys_are_rejected(self):
        fc={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'id':'x'},'geometry':{'type':'Point','coordinates':[0,0]}},{'type':'Feature','properties':{'id':'x'},'geometry':{'type':'Point','coordinates':[1,1]}}]}
        with self.assertRaisesRegex(ValueError,'duplicate'):visual_geometry_diff(fc,{'type':'FeatureCollection','features':[]})

if __name__=='__main__':unittest.main()
