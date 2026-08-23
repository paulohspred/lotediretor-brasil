from __future__ import annotations
import importlib.util, os, sys
from pathlib import Path

R=Path(__file__).resolve().parents[1]
DP=R/'workers'/'data-pipelines'
sys.path.insert(0,str(DP))
os.environ.pop('PLATFORM_DATABASE_URL',None)

spec=importlib.util.spec_from_file_location('municipality_lab_rc3',DP/'municipality_lab.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
assert mod.DB==''

profile=mod.load_profile(str(R/'data/municipality-labs/sao-paulo-3550308.json'))

def fake_fetch(source_spec):
    assert source_spec['mode']=='WFS'
    assert source_spec['srs_name']=='EPSG:4326'
    return ({'type':'FeatureCollection','features':[{
        'type':'Feature','id':'fixture.1','geometry':{'type':'Polygon','coordinates':[[[-46.7,-23.6],[-46.6,-23.6],[-46.6,-23.5],[-46.7,-23.6]]]},
        'properties':{'fixture_code':'Z1','name':'Fixture'}
    }]},{'mode':'WFS','pages':1,'url':'fixture://offline'})

mod.fetch_feature_collection=fake_fetch
out=mod.inspect_wfs(profile,'SP_GEOSAMPA_WFS','geoportal:lote_cidadao','EPSG:4326')
assert out['status']=='INSPECTED'
assert 'fixture_code' in out['property_keys']
assert out['sample'][0]['id']=='fixture.1'

# A DB-backed command must fail explicitly, rather than failing at module import time.
try:
    mod.bootstrap(profile)
except RuntimeError as exc:
    assert 'PLATFORM_DATABASE_URL_required_for_db_command' in str(exc)
else:
    raise AssertionError('bootstrap should require DB configuration')

print('v19-rc3 Sao Paulo inspection tooling lazy-DB OK')
