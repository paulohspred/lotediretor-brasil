import os,sys,unittest
from unittest.mock import Mock
os.environ.setdefault('PLATFORM_DATABASE_URL','postgresql://unused')
sys.path.insert(0,'workers/data-pipelines')
from connectors import fetch_feature_collection,_quality

class FakeSession:
    def __init__(self,payloads):self.payloads=list(payloads);self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs));payload=self.payloads.pop(0);r=Mock();r.status_code=200;r.url=url;r.raise_for_status=lambda:None;r.json=lambda:payload;return r

class ConnectorTests(unittest.TestCase):
    def test_geojson_single(self):
        s=FakeSession([{'type':'FeatureCollection','features':[{'id':1,'geometry':{'type':'Point','coordinates':[0,0]},'properties':{}}]}])
        p,m=fetch_feature_collection({'code':'CAR','url':'https://example.test/data','mode':'GEOJSON'},s)
        self.assertEqual(len(p['features']),1);self.assertEqual(m['pages'],1)
    def test_wfs_paginates_without_partial_publish(self):
        os.environ['CAR_SOURCE_PAGE_SIZE']='2';os.environ['CAR_SOURCE_MAX_PAGES']='3'
        f=lambda i:{'id':i,'geometry':{'type':'Point','coordinates':[i,0]},'properties':{}}
        s=FakeSession([{'type':'FeatureCollection','features':[f(1),f(2)]},{'type':'FeatureCollection','features':[f(3)]}])
        p,m=fetch_feature_collection({'code':'CAR','url':'https://example.test/wfs','mode':'WFS','typename':'layer'},s)
        self.assertEqual([x['id'] for x in p['features']],[1,2,3]);self.assertEqual(m['pages'],2)
    def test_wfs_requests_explicit_output_crs(self):
        os.environ['CAR_SOURCE_PAGE_SIZE']='2';os.environ['CAR_SOURCE_MAX_PAGES']='2'
        f={'id':1,'geometry':{'type':'Point','coordinates':[0,0]},'properties':{}}
        s=FakeSession([{'type':'FeatureCollection','features':[f]}])
        fetch_feature_collection({'code':'CAR','url':'https://example.test/wfs','mode':'WFS','typename':'layer','srs_name':'EPSG:4326'},s)
        self.assertEqual(s.calls[0][1]['params']['srsName'],'EPSG:4326')


    def test_quality_rejects_projected_coordinates_mislabeled_as_4326(self):
        q=_quality({'type':'FeatureCollection','features':[{'id':1,'geometry':{'type':'Point','coordinates':[333000,7394000]},'properties':{}}]})
        self.assertTrue(any(x['code']=='epsg4326_coordinate_range' and x['status']=='FAIL' for x in q))

    def test_quality_rejects_geometryless_features(self):
        q=_quality({'type':'FeatureCollection','features':[{'id':1,'geometry':None,'properties':{}}]})
        self.assertTrue(any(x['code']=='geometry_presence' and x['status']=='FAIL' for x in q))

if __name__=='__main__':unittest.main()
