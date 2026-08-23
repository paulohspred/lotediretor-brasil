import sys,zipfile,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'workers'/'rural-export'))
from exporter import kml_document,package_export

def poly(x=0,y=0):return {'type':'Polygon','coordinates':[[[x,y],[x+1,y],[x+1,y+1],[x,y+1],[x,y]]]}
a={'name':'Fazenda <Teste>','geometry':poly()};records=[{'registry_type':'CAR','official_identifier':'CAR&1','geometry':poly(0.1,0.1)},{'registry_type':'SNCR','official_identifier':'123','geometry':None}]
kml=kml_document(a,records)
assert b'&lt;Teste&gt;' in kml and b'CAR&amp;1' in kml
assert kml.count(b'<Placemark>')==2
payload,ext,ctype=package_export(kml,'KMZ');assert ext=='kmz' and ctype.endswith('kmz')
with zipfile.ZipFile(io.BytesIO(payload)) as z:assert z.read('doc.kml')==kml
payload2,ext2,_=package_export(kml,'KML');assert payload2==kml and ext2=='kml'
print('rural export v17 OK')
