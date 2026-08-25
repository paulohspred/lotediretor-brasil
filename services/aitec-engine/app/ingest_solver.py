from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
import struct
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from shapely import wkb
from shapely.geometry import LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon, mapping

INGEST_VERSION = 'aitec-ingest-v20.1'


def _feature(geometry, properties: dict | None = None) -> dict:
    return {'type': 'Feature', 'properties': properties or {}, 'geometry': mapping(geometry)}


def _result(fmt: str, payload: bytes, features: list[dict], *, crs: str | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        'status': 'PARSED',
        'ingest_version': INGEST_VERSION,
        'format': fmt,
        'input_sha256': hashlib.sha256(payload).hexdigest(),
        'feature_count': len(features),
        'crs': crs,
        'feature_collection': {'type': 'FeatureCollection', 'features': features},
        'warnings': warnings or [],
        'policy': 'CRS, attributes and provenance are preserved when present; missing CRS is never guessed.',
    }


def ingest_geojson(payload: bytes) -> dict[str, Any]:
    doc = json.loads(payload.decode('utf-8-sig'))
    if doc.get('type') == 'FeatureCollection':
        features = doc.get('features') or []
    elif doc.get('type') == 'Feature':
        features = [doc]
    elif doc.get('type') in ('Point','MultiPoint','LineString','MultiLineString','Polygon','MultiPolygon','GeometryCollection'):
        features = [{'type':'Feature','properties':{},'geometry':doc}]
    else:
        raise ValueError('unsupported GeoJSON root type')
    crs = None
    if isinstance(doc.get('crs'), dict):
        crs = json.dumps(doc['crs'], ensure_ascii=False, sort_keys=True)
    return _result('GEOJSON', payload, features, crs=crs, warnings=[] if crs else ['GeoJSON has no explicit CRS metadata; coordinates were not reprojected.'])


def _kml_coordinates(text: str | None) -> list[tuple]:
    out=[]
    for token in (text or '').strip().split():
        parts=token.split(',')
        if len(parts)<2:continue
        values=[float(parts[0]),float(parts[1])]
        if len(parts)>2 and parts[2] != '':values.append(float(parts[2]))
        out.append(tuple(values))
    return out


def _local(tag: str) -> str:
    return tag.rsplit('}',1)[-1]


def _kml_geom(element):
    kind=_local(element.tag)
    if kind=='Point':
        coords=_kml_coordinates(next((child.text for child in element.iter() if _local(child.tag)=='coordinates'),None));return Point(coords[0]) if coords else None
    if kind=='LineString':
        coords=_kml_coordinates(next((child.text for child in element.iter() if _local(child.tag)=='coordinates'),None));return LineString(coords) if len(coords)>=2 else None
    if kind=='Polygon':
        rings=[]
        for ring in [node for node in element.iter() if _local(node.tag)=='LinearRing']:
            coords=_kml_coordinates(next((child.text for child in ring.iter() if _local(child.tag)=='coordinates'),None))
            if len(coords)>=4:rings.append(coords)
        return Polygon(rings[0],rings[1:]) if rings else None
    if kind=='MultiGeometry':
        geoms=[]
        for child in element:
            if _local(child.tag) in ('Point','LineString','Polygon','MultiGeometry'):
                geom=_kml_geom(child)
                if geom is not None and not geom.is_empty:geoms.append(geom)
        if not geoms:return None
        types={g.geom_type for g in geoms}
        if types=={'Point'}:return MultiPoint(geoms)
        if types=={'LineString'}:return MultiLineString(geoms)
        if types=={'Polygon'}:return MultiPolygon(geoms)
        from shapely.geometry import GeometryCollection
        return GeometryCollection(geoms)
    return None


def ingest_kml(payload: bytes, fmt: str = 'KML') -> dict[str, Any]:
    root=ET.fromstring(payload)
    features=[]
    placemarks=[node for node in root.iter() if _local(node.tag)=='Placemark']
    for index,pm in enumerate(placemarks):
        props={}
        name=next((child.text for child in pm if _local(child.tag)=='name'),None)
        description=next((child.text for child in pm if _local(child.tag)=='description'),None)
        if name is not None:props['name']=name
        if description is not None:props['description']=description
        geom=None
        for node in pm.iter():
            if _local(node.tag) in ('Point','LineString','Polygon','MultiGeometry'):
                geom=_kml_geom(node);break
        if geom is not None and not geom.is_empty:features.append(_feature(geom,props))
    return _result(fmt,payload,features,crs='EPSG:4326',warnings=[])


def ingest_kmz(payload: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        candidates=sorted(name for name in archive.namelist() if name.lower().endswith('.kml'))
        if not candidates:raise ValueError('KMZ contains no KML document')
        kml=archive.read('doc.kml' if 'doc.kml' in candidates else candidates[0])
    parsed=ingest_kml(kml,'KMZ');parsed['input_sha256']=hashlib.sha256(payload).hexdigest();parsed['container_kml_sha256']=hashlib.sha256(kml).hexdigest();return parsed


def _dbf_records(payload: bytes) -> list[dict]:
    if len(payload)<32:raise ValueError('invalid DBF header')
    header_len=struct.unpack_from('<H',payload,8)[0];record_len=struct.unpack_from('<H',payload,10)[0]
    fields=[];offset=32
    while offset+32<=header_len and payload[offset]!=0x0D:
        desc=payload[offset:offset+32];name=desc[:11].split(b'\x00',1)[0].decode('latin-1').strip();kind=chr(desc[11]);length=desc[16];decimals=desc[17];fields.append((name,kind,length,decimals));offset+=32
    records=[]
    pos=header_len
    while pos+record_len<=len(payload) and payload[pos]!=0x1A:
        raw=payload[pos:pos+record_len];deleted=raw[:1]==b'*';cursor=1;row={'_deleted':deleted} if deleted else {}
        for name,kind,length,decimals in fields:
            text=raw[cursor:cursor+length].decode('latin-1').strip();cursor+=length
            value:Any=text
            if text=='':value=None
            elif kind in ('N','F'):
                try:value=float(text) if decimals or '.' in text else int(text)
                except ValueError:value=text
            elif kind=='L':value=text.upper() in ('Y','T')
            row[name]=value
        records.append(row);pos+=record_len
    return records


def _shape_record(content: bytes):
    if len(content)<4:return None
    st=struct.unpack_from('<i',content,0)[0]
    base={11:1,13:3,15:5,18:8}.get(st,st)
    if base==0:return None
    if base==1:
        return Point(struct.unpack_from('<dd',content,4))
    if base in (3,5):
        if len(content)<44:raise ValueError('truncated SHP poly record')
        num_parts,num_points=struct.unpack_from('<ii',content,36);parts=list(struct.unpack_from('<'+'i'*num_parts,content,44)) if num_parts else []
        pstart=44+4*num_parts;points=[struct.unpack_from('<dd',content,pstart+i*16) for i in range(num_points)]
        ranges=parts+[num_points];segments=[points[ranges[i]:ranges[i+1]] for i in range(len(parts))]
        if base==3:
            lines=[LineString(segment) for segment in segments if len(segment)>=2];return lines[0] if len(lines)==1 else MultiLineString(lines)
        rings=[segment for segment in segments if len(segment)>=4]
        ring_polys=[Polygon(ring) for ring in rings if Polygon(ring).is_valid and not Polygon(ring).is_empty]
        outers=[];holes:dict[int,list]= {}
        for poly in sorted(ring_polys,key=lambda g:g.area,reverse=True):
            parent=None
            for idx,outer in enumerate(outers):
                if outer.covers(poly.representative_point()):parent=idx;break
            if parent is None:outers.append(poly);holes[len(outers)-1]=[]
            else:holes[parent].append(list(poly.exterior.coords))
        polys=[Polygon(list(outer.exterior.coords),holes.get(i,[])) for i,outer in enumerate(outers)]
        return polys[0] if len(polys)==1 else MultiPolygon(polys)
    if base==8:
        if len(content)<40:raise ValueError('truncated SHP multipoint record')
        num_points=struct.unpack_from('<i',content,36)[0];points=[struct.unpack_from('<dd',content,40+i*16) for i in range(num_points)];return MultiPoint(points)
    raise ValueError(f'unsupported shapefile shape type:{st}')


def ingest_shapefile(shp_payload: bytes, dbf_payload: bytes | None = None, prj_payload: bytes | None = None) -> dict[str, Any]:
    if len(shp_payload)<100 or struct.unpack_from('>i',shp_payload,0)[0]!=9994:raise ValueError('invalid SHP header')
    records=[];pos=100
    while pos+8<=len(shp_payload):
        _,words=struct.unpack_from('>ii',shp_payload,pos);pos+=8;size=words*2
        if pos+size>len(shp_payload):raise ValueError('truncated SHP record')
        geom=_shape_record(shp_payload[pos:pos+size]);pos+=size
        records.append(geom)
    attrs=_dbf_records(dbf_payload) if dbf_payload else []
    features=[]
    for index,geom in enumerate(records):
        if geom is None or geom.is_empty:continue
        props=attrs[index] if index<len(attrs) else {}
        features.append(_feature(geom,props))
    crs=prj_payload.decode('utf-8-sig','replace').strip() if prj_payload else None
    warnings=[]
    if dbf_payload is None:warnings.append('DBF companion not supplied; attributes are empty.')
    if crs is None:warnings.append('PRJ companion not supplied; CRS was not guessed.')
    return _result('SHP',shp_payload,features,crs=crs,warnings=warnings)


def _gpkg_wkb(blob: bytes) -> bytes:
    if len(blob)<8 or blob[:2]!=b'GP':raise ValueError('invalid GeoPackage geometry header')
    flags=blob[3];little=bool(flags&1);order='<' if little else '>';envelope_code=(flags>>1)&7
    envelope_doubles={0:0,1:4,2:6,3:6,4:8}.get(envelope_code)
    if envelope_doubles is None:raise ValueError('unsupported GeoPackage envelope code')
    header=8+envelope_doubles*8
    if len(blob)<=header:raise ValueError('truncated GeoPackage geometry')
    struct.unpack_from(order+'i',blob,4)[0]
    return blob[header:]


def ingest_gpkg(payload: bytes) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(suffix='.gpkg') as tmp:
        tmp.write(payload);tmp.flush();conn=sqlite3.connect(tmp.name);conn.row_factory=sqlite3.Row
        try:
            rows=conn.execute('SELECT table_name,column_name,srs_id FROM gpkg_geometry_columns ORDER BY table_name').fetchall()
        except sqlite3.Error as exc:
            conn.close();raise ValueError(f'invalid GeoPackage metadata:{exc}') from exc
        features=[];srs_ids=set()
        for meta in rows:
            table=meta['table_name'];column=meta['column_name'];srs_ids.add(int(meta['srs_id']))
            safe_table='"'+str(table).replace('"','""')+'"';safe_col='"'+str(column).replace('"','""')+'"'
            query=f'SELECT rowid AS __rowid__, * FROM {safe_table}'
            for row in conn.execute(query):
                blob=row[column]
                if blob is None:continue
                geom=wkb.loads(_gpkg_wkb(bytes(blob)))
                props={key:row[key] for key in row.keys() if key not in (column,'__rowid__')};props['_table']=table;props['_rowid']=row['__rowid__']
                features.append(_feature(geom,props))
        crs='GPKG_SRS_IDS:'+','.join(str(x) for x in sorted(srs_ids)) if srs_ids else None
        conn.close()
    return _result('GPKG',payload,features,crs=crs,warnings=[] if crs else ['No geometry CRS metadata found.'])


def ingest_dxf(payload: bytes) -> dict[str, Any]:
    if payload[:22].startswith(b'AutoCAD Binary DXF'):raise ValueError('binary DXF is not supported; provide ASCII DXF')
    text=payload.decode('utf-8-sig','replace');raw=text.replace('\r','').split('\n');pairs=[]
    for i in range(0,len(raw)-1,2):
        try:code=int(raw[i].strip())
        except ValueError:continue
        pairs.append((code,raw[i+1].strip()))
    entities=[];i=0;in_entities=False;warnings=[]
    while i<len(pairs):
        code,value=pairs[i]
        if code==0 and value=='SECTION' and i+1<len(pairs) and pairs[i+1]==(2,'ENTITIES'):in_entities=True;i+=2;continue
        if in_entities and code==0 and value=='ENDSEC':break
        if not in_entities or code!=0:i+=1;continue
        kind=value;data=[];i+=1
        while i<len(pairs) and pairs[i][0]!=0:data.append(pairs[i]);i+=1
        vals:dict[int,list[str]]={}
        for c,v in data:vals.setdefault(c,[]).append(v)
        layer=(vals.get(8) or ['0'])[0]
        try:
            if kind=='POINT':geom=Point(float(vals[10][0]),float(vals[20][0]))
            elif kind=='LINE':geom=LineString([(float(vals[10][0]),float(vals[20][0])),(float(vals[11][0]),float(vals[21][0]))])
            elif kind=='LWPOLYLINE':
                xs=vals.get(10,[]);ys=vals.get(20,[]);coords=[(float(x),float(y)) for x,y in zip(xs,ys)];closed=int((vals.get(70) or ['0'])[0])&1
                geom=Polygon(coords) if closed and len(coords)>=3 else LineString(coords)
            else:warnings.append(f'Unsupported DXF entity skipped:{kind}');continue
            entities.append(_feature(geom,{'layer':layer,'entity_type':kind}))
        except (KeyError,ValueError,IndexError) as exc:warnings.append(f'Invalid DXF {kind} skipped:{exc}')
    return _result('DXF',payload,entities,crs=None,warnings=warnings+['DXF CRS/units are not inferred; source coordinates are preserved.'])


def ingest_ifc(payload: bytes) -> dict[str, Any]:
    text=payload.decode('utf-8-sig','replace')
    point_re=re.compile(r"#(\d+)\s*=\s*IFCCARTESIANPOINT\s*\(\(([^)]*)\)\)\s*;",re.I)
    line_re=re.compile(r"#(\d+)\s*=\s*IFCPOLYLINE\s*\(\(([^)]*)\)\)\s*;",re.I)
    points={}
    for match in point_re.finditer(text):
        values=[float(v.strip()) for v in match.group(2).split(',') if v.strip()]
        if len(values)>=2:points[match.group(1)]=tuple(values[:3])
    features=[];warnings=[]
    for match in line_re.finditer(text):
        ids=re.findall(r'#(\d+)',match.group(2));coords=[points[i] for i in ids if i in points]
        if len(coords)>=2:features.append(_feature(LineString(coords),{'ifc_entity_id':int(match.group(1)),'entity_type':'IFCPOLYLINE'}))
        else:warnings.append(f'IFCPOLYLINE #{match.group(1)} has unresolved points')
    if not features:warnings.append('No IFC polyline geometry extracted; unsupported BREP/CSG/tessellated representations are preserved only in the source hash.')
    return _result('IFC',payload,features,crs=None,warnings=warnings+['IFC map conversion/CRS is not inferred by this adapter.'])


def _companion(companions: dict[str,bytes] | None, suffix: str) -> bytes | None:
    for name,payload in (companions or {}).items():
        if str(name).lower().endswith(suffix.lower()):return payload
    return None


def ingest_dataset(filename: str, payload: bytes, companions: dict[str,bytes] | None = None) -> dict[str, Any]:
    ext=Path(filename).suffix.lower()
    if ext in ('.json','.geojson'):return ingest_geojson(payload)
    if ext=='.kml':return ingest_kml(payload)
    if ext=='.kmz':return ingest_kmz(payload)
    if ext=='.shp':return ingest_shapefile(payload,_companion(companions,'.dbf'),_companion(companions,'.prj'))
    if ext=='.gpkg':return ingest_gpkg(payload)
    if ext=='.dxf':return ingest_dxf(payload)
    if ext=='.ifc':return ingest_ifc(payload)
    raise ValueError(f'unsupported ingest extension:{ext or "<none>"}')
