import os,sys,unittest
os.environ.setdefault('PLATFORM_DATABASE_URL','postgresql://invalid/invalid')
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','workers','data-pipelines'))
import connectors
class T(unittest.TestCase):
 def test_ckan_resource(self):
  p={'result':{'resources':[{'format':'CSV','url':'x.csv'},{'format':'SHP-ZIP','name':'Áreas embargadas polígonos','url':'https://official/data.zip'}]}}
  self.assertEqual(connectors._ckan_shp_resource(p),'https://official/data.zip')
 def test_sources_default_disabled(self):
  old=dict(os.environ)
  try:
   for c in ['CAR','SIGEF','IBAMA_EMBARGO','PRODES']:
    os.environ[f'{c}_SOURCE_URL']='https://official.invalid/source';os.environ.pop(f'{c}_SOURCE_ENABLED',None)
   self.assertEqual(connectors.configured_geojson_sources(),[])
  finally: os.environ.clear();os.environ.update(old)
if __name__=='__main__':unittest.main()
