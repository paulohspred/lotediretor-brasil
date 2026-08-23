import os,sys,unittest
os.environ.setdefault('PLATFORM_DATABASE_URL','postgresql://unused')
sys.path.insert(0,'workers/documents')
from rules import legal_units, legal_candidates

class LegalV19Tests(unittest.TestCase):
    def test_article_page_hierarchy(self):
        text='''<<<PAGE:1>>>\nCAPÍTULO I - Do Zoneamento\nArt. 12. A taxa de ocupação máxima: 60%.\n§ 1º O recuo frontal: 5 m.\n<<<PAGE:2>>>\nArt. 13. A taxa de permeabilidade mínima: 25%.'''
        units=legal_units(text);arts=[x for x in units if x['article_type']=='ARTICLE']
        self.assertEqual([x['label'] for x in arts],['12','13'])
        self.assertEqual(arts[0]['source_locator'],'page:1#art:12')
        self.assertEqual(arts[1]['source_locator'],'page:2#art:13')
        c=legal_candidates(arts[0]['body_text'],arts[0]['source_locator'])
        by={x['parameter']:x for x in c}
        self.assertEqual(by['TO_MAX']['value'],60.0);self.assertEqual(by['TO_MAX']['unit'],'%')
        self.assertEqual(by['SETBACK_FRONT_M']['value'],5.0)
    def test_percent_requires_percent_semantics(self):
        self.assertFalse(any(x['parameter']=='TO_MAX' for x in legal_candidates('Taxa de ocupação máxima 60 sem símbolo.')))

if __name__=='__main__':unittest.main()
