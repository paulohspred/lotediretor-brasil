from pathlib import Path
import os
import sqlite3
import struct
import sys
import tempfile
import unittest

from shapely.geometry import Point
from shapely import wkb

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'services'/'aitec-engine'/'app'))
from export_solver import export_dxf,export_ifc,export_kml,export_kmz  # noqa:E402
from ingest_solver import INGEST_VERSION,ingest_dataset  # noqa:E402

FC={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'name':'P1'},'geometry':{'type':'Point','coordinates':[1,2]}},{'type':'Feature','properties':{'name':'Lot'},'geometry':{'type':'Polygon','coordinates':[[[0,0],[10,0],[10,10],[0,10],[0,0]]]}}]}

def point_shp(x=1.0,y=2.0):
    content=struct.pack('<i2d',1,x,y);total=100+8+len(content);header=bytearray(100);struct.pack_into('>i',header,0,9994);struct.pack_into('>i',header,24,total//2);struct.pack_into('<i',header,28,1000);struct.pack_into('<i',header,32,1);struct.pack_into('<4d',header,36,x,y,x,y);record=struct.pack('>2i',1,len(content)//2)+content;return bytes(header)+record

def simple_dbf(name='Alpha'):
    header_len=65;record_len=11;buf=bytearray(header_len+record_len+1);buf[0]=3;struct.pack_into('<I',buf,4,1);struct.pack_into('<H',buf,8,header_len);struct.pack_into('<H',buf,10,record_len);field=bytearray(32);field[:4]=b'NAME';field[11]=ord('C');field[16]=10;buf[32:64]=field;buf[64]=0x0D;buf[65]=0x20;buf[66:76]=name.encode('ascii').ljust(10,b' ');buf[-1]=0x1A;return bytes(buf)

def gpkg_bytes():
    fd,path=tempfile.mkstemp(suffix='.gpkg');os.close(fd)
    try:
        conn=sqlite3.connect(path);conn.executescript('CREATE TABLE gpkg_geometry_columns (table_name TEXT,column_name TEXT,geometry_type_name TEXT,srs_id INTEGER,z TINYINT,m TINYINT);CREATE TABLE lots (id INTEGER PRIMARY KEY,name TEXT,geom BLOB);');conn.execute("INSERT INTO gpkg_geometry_columns VALUES ('lots','geom','POINT',4326,0,0)");blob=b'GP\x00\x01'+struct.pack('<i',4326)+wkb.dumps(Point(5,6));conn.execute('INSERT INTO lots(name,geom) VALUES (?,?)',('A',blob));conn.commit();conn.close();return Path(path).read_bytes()
    finally:
        if os.path.exists(path):os.unlink(path)

class IngestV20Tests(unittest.TestCase):
    def test_geojson_kml_kmz_roundtrip(self):
        import json
        geo=ingest_dataset('data.geojson',json.dumps(FC).encode());self.assertEqual(geo['feature_count'],2);self.assertEqual(geo['ingest_version'],INGEST_VERSION)
        kml=ingest_dataset('data.kml',export_kml(FC));self.assertEqual(kml['feature_count'],2);self.assertEqual(kml['crs'],'EPSG:4326')
        kmz=ingest_dataset('data.kmz',export_kmz(FC));self.assertEqual(kmz['feature_count'],2);self.assertIn('container_kml_sha256',kmz)

    def test_shp_dbf_prj_are_parsed_without_guessing(self):
        result=ingest_dataset('point.shp',point_shp(),{'point.dbf':simple_dbf(),'point.prj':b'EPSG:4326'})
        self.assertEqual(result['format'],'SHP');self.assertEqual(result['feature_count'],1);self.assertEqual(result['feature_collection']['features'][0]['properties']['NAME'],'Alpha');self.assertEqual(result['crs'],'EPSG:4326')
        no_prj=ingest_dataset('point.shp',point_shp(),{'point.dbf':simple_dbf()});self.assertIsNone(no_prj['crs']);self.assertTrue(any('not guessed' in w for w in no_prj['warnings']))

    def test_geopackage_geometry_and_attributes(self):
        result=ingest_dataset('lots.gpkg',gpkg_bytes());self.assertEqual(result['format'],'GPKG');self.assertEqual(result['feature_count'],1);feature=result['feature_collection']['features'][0];self.assertEqual(feature['properties']['name'],'A');self.assertEqual(feature['geometry']['type'],'Point');self.assertIn('4326',result['crs'])

    def test_ascii_dxf_and_ifc_from_exporters_are_ingested(self):
        dxf=ingest_dataset('model.dxf',export_dxf(FC));self.assertGreaterEqual(dxf['feature_count'],2);self.assertTrue(any('CRS/units are not inferred' in w for w in dxf['warnings']))
        ifc=ingest_dataset('model.ifc',export_ifc({'type':'FeatureCollection','features':[FC['features'][1]]}));self.assertGreaterEqual(ifc['feature_count'],1);self.assertEqual(ifc['feature_collection']['features'][0]['properties']['entity_type'],'IFCPOLYLINE')

    def test_unknown_extension_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'unsupported ingest extension'):ingest_dataset('data.xyz',b'123')

if __name__=='__main__':unittest.main()
