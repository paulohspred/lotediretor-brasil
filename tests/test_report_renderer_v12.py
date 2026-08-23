import os,sys,unittest,hashlib
os.environ.setdefault('PLATFORM_DATABASE_URL','postgresql://invalid/invalid')
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','workers','reports'))
import renderer as reports
class T(unittest.TestCase):
 def test_pdf_renderer(self):
  raw=reports.render('LoteDiretor test',['Parcela: 123','Data-base: 2026-08-21','Evidência: rule-1'])
  self.assertTrue(raw.startswith(b'%PDF'))
  self.assertGreater(len(raw),500)
  self.assertEqual(len(hashlib.sha256(raw).hexdigest()),64)
if __name__=='__main__':unittest.main()
