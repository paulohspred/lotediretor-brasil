from pathlib import Path
import base64
import hashlib
import io
import json
import sys
import unittest
import zipfile
from xml.etree import ElementTree

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services'/'aitec-engine'/'app'))
from export_solver import EXPORT_VERSION,export_dxf,export_geojson,export_gltf,export_ifc,export_kmz,export_manifest,export_pdf,export_xlsx  # noqa:E402

FC={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'name':'Tower A','layer':'BUILDING','height_m':12},'geometry':{'type':'Polygon','coordinates':[[[0,0],[10,0],[10,8],[0,8],[0,0]]]}}]}

class ExportV20Tests(unittest.TestCase):
    def test_geojson_kmz_dxf_ifc_are_generated(self):
        geo=export_geojson(FC);self.assertEqual(json.loads(geo)['type'],'FeatureCollection')
        kmz=export_kmz(FC)
        with zipfile.ZipFile(io.BytesIO(kmz)) as z:
            self.assertEqual(z.namelist(),['doc.kml']);self.assertIn(b'<Placemark>',z.read('doc.kml'))
        dxf=export_dxf(FC);self.assertIn(b'LWPOLYLINE',dxf);self.assertTrue(dxf.rstrip().endswith(b'EOF'))
        ifc=export_ifc(FC,'Demo Project');self.assertTrue(ifc.startswith(b'ISO-10303-21;'));self.assertIn(b"FILE_SCHEMA(('IFC4'))",ifc);self.assertIn(b'IFCBUILDINGELEMENTPROXY',ifc)

    def test_xlsx_is_valid_openxml_zip(self):
        payload=export_xlsx({'Summary':[{'metric':'VGV','value':1000},{'metric':'CAPEX','value':700}]})
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            names=set(z.namelist());self.assertIn('[Content_Types].xml',names);self.assertIn('xl/workbook.xml',names);self.assertIn('xl/worksheets/sheet1.xml',names)
            ElementTree.fromstring(z.read('xl/workbook.xml'));ElementTree.fromstring(z.read('xl/worksheets/sheet1.xml'))

    def test_pdf_has_header_xref_and_eof(self):
        payload=export_pdf('A.I TEC report',['VGV: 1000','CAPEX: 700'])
        self.assertTrue(payload.startswith(b'%PDF-1.4'));self.assertIn(b'xref',payload);self.assertTrue(payload.rstrip().endswith(b'%%EOF'))

    def test_gltf_embeds_mesh_buffer(self):
        payload=export_gltf(FC);doc=json.loads(payload);self.assertEqual(doc['asset']['version'],'2.0');self.assertEqual(doc['meshes'][0]['primitives'][0]['attributes']['POSITION'],0)
        uri=doc['buffers'][0]['uri'];self.assertTrue(uri.startswith('data:application/octet-stream;base64,'));raw=base64.b64decode(uri.split(',',1)[1]);self.assertEqual(len(raw),doc['buffers'][0]['byteLength']);self.assertGreater(doc['accessors'][0]['count'],0)

    def test_manifest_hashes_exact_bytes(self):
        files={'model.geojson':export_geojson(FC),'report.pdf':export_pdf('x',['y'])};manifest=export_manifest(files)
        self.assertEqual(manifest['version'],EXPORT_VERSION)
        for name,payload in files.items():self.assertEqual(manifest['files'][name]['sha256'],hashlib.sha256(payload).hexdigest())

    def test_gltf_refuses_no_polygon_mesh(self):
        with self.assertRaisesRegex(ValueError,'Polygon'):
            export_gltf({'type':'FeatureCollection','features':[{'type':'Feature','properties':{},'geometry':{'type':'Point','coordinates':[0,0]}}]})

if __name__=='__main__':unittest.main()
