import os,sys,unittest
os.environ.setdefault('PLATFORM_DATABASE_URL','postgresql://unused')
sys.path.insert(0,'workers/documents')
from rules import legal_candidates

class LegalConditionTests(unittest.TestCase):
    def test_area_condition_attached_to_ca(self):
        txt='Para lotes com área até 500 m², o coeficiente de aproveitamento máximo: 2,0.'
        items=legal_candidates(txt,'page:7#art:21')
        ca=next(x for x in items if x['parameter']=='CA_MAX')
        self.assertEqual(ca['condition'],{'field':'lot_area_m2','op':'lte','value':500.0})
        self.assertEqual(ca['source_locator'],'page:7#art:21')
    def test_conditional_corner_lot(self):
        txt='Para lotes de esquina, o recuo frontal: 5 m.'
        item=next(x for x in legal_candidates(txt) if x['parameter']=='SETBACK_FRONT_M')
        self.assertEqual(item['condition'],{'field':'corner_lot','op':'eq','value':True})
    def test_extractor_metadata_not_in_condition(self):
        item=next(x for x in legal_candidates('Coeficiente de aproveitamento básico: 1,0.') if x['parameter']=='CA_BASIC')
        self.assertEqual(item['condition'],{})
        self.assertEqual(item['extractor'],'deterministic_legal_v19_beta')

if __name__=='__main__':unittest.main()
