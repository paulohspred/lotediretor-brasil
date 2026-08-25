from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import struct
import zipfile
from html import escape
from typing import Any

from shapely.geometry import shape
from shapely.ops import triangulate

EXPORT_VERSION = 'aitec-export-v20.1'
IFC64 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$'


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def export_geojson(feature_collection: dict) -> bytes:
    if feature_collection.get('type') != 'FeatureCollection' or not isinstance(feature_collection.get('features'), list):
        raise ValueError('GeoJSON export requires FeatureCollection')
    return _canonical_json(feature_collection)


def _kml_geometry(geometry: dict) -> str:
    kind = geometry.get('type')
    coords = geometry.get('coordinates')
    def seq(points):
        return ' '.join(','.join(str(float(v)) for v in point[:3]) for point in points)
    if kind == 'Point':
        return f'<Point><coordinates>{seq([coords])}</coordinates></Point>'
    if kind == 'LineString':
        return f'<LineString><tessellate>1</tessellate><coordinates>{seq(coords)}</coordinates></LineString>'
    if kind == 'Polygon':
        if not coords:
            return ''
        outer = f'<outerBoundaryIs><LinearRing><coordinates>{seq(coords[0])}</coordinates></LinearRing></outerBoundaryIs>'
        inners = ''.join(f'<innerBoundaryIs><LinearRing><coordinates>{seq(ring)}</coordinates></LinearRing></innerBoundaryIs>' for ring in coords[1:])
        return f'<Polygon>{outer}{inners}</Polygon>'
    if kind in ('MultiPoint', 'MultiLineString', 'MultiPolygon'):
        subtype = {'MultiPoint': 'Point', 'MultiLineString': 'LineString', 'MultiPolygon': 'Polygon'}[kind]
        return '<MultiGeometry>' + ''.join(_kml_geometry({'type': subtype, 'coordinates': part}) for part in coords) + '</MultiGeometry>'
    if kind == 'GeometryCollection':
        return '<MultiGeometry>' + ''.join(_kml_geometry(part) for part in geometry.get('geometries', [])) + '</MultiGeometry>'
    raise ValueError(f'unsupported KML geometry:{kind}')


def export_kml(feature_collection: dict, document_name: str = 'LoteDiretor A.I TEC') -> bytes:
    export_geojson(feature_collection)
    placemarks = []
    for index, feature in enumerate(feature_collection['features']):
        props = feature.get('properties') or {}
        name = escape(str(props.get('name') or props.get('id') or f'Feature {index + 1}'))
        description = escape(json.dumps(props, ensure_ascii=False, sort_keys=True))
        placemarks.append(f'<Placemark><name>{name}</name><description>{description}</description>{_kml_geometry(feature["geometry"])}</Placemark>')
    xml = '<?xml version="1.0" encoding="UTF-8"?>' + '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>' + f'<name>{escape(document_name)}</name>' + ''.join(placemarks) + '</Document></kml>'
    return xml.encode('utf-8')


def export_kmz(feature_collection: dict, document_name: str = 'LoteDiretor A.I TEC') -> bytes:
    payload = export_kml(feature_collection, document_name)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo('doc.kml', date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, payload)
    return buffer.getvalue()


def _dxf_entities(geometry: dict, layer: str, out: list[str]):
    kind = geometry.get('type')
    coords = geometry.get('coordinates')
    if kind == 'Point':
        out.extend(['0','POINT','8',layer,'10',str(float(coords[0])),'20',str(float(coords[1])),'30',str(float(coords[2]) if len(coords)>2 else 0.0)])
    elif kind == 'LineString':
        out.extend(['0','LWPOLYLINE','8',layer,'90',str(len(coords)),'70','0'])
        for point in coords:
            out.extend(['10',str(float(point[0])),'20',str(float(point[1]))])
    elif kind == 'Polygon':
        if coords:
            ring = coords[0]
            if len(ring) > 1 and ring[0][:2] == ring[-1][:2]:
                ring = ring[:-1]
            out.extend(['0','LWPOLYLINE','8',layer,'90',str(len(ring)),'70','1'])
            for point in ring:
                out.extend(['10',str(float(point[0])),'20',str(float(point[1]))])
    elif kind in ('MultiPoint','MultiLineString','MultiPolygon'):
        subtype={'MultiPoint':'Point','MultiLineString':'LineString','MultiPolygon':'Polygon'}[kind]
        for part in coords:_dxf_entities({'type':subtype,'coordinates':part},layer,out)
    elif kind == 'GeometryCollection':
        for part in geometry.get('geometries',[]):_dxf_entities(part,layer,out)
    else:
        raise ValueError(f'unsupported DXF geometry:{kind}')


def export_dxf(feature_collection: dict) -> bytes:
    export_geojson(feature_collection)
    lines=['0','SECTION','2','HEADER','0','ENDSEC','0','SECTION','2','ENTITIES']
    for index,feature in enumerate(feature_collection['features']):
        layer=re.sub(r'[^A-Za-z0-9_-]+','_',str((feature.get('properties') or {}).get('layer') or f'AITEC_{index+1}'))[:80] or 'AITEC'
        _dxf_entities(feature['geometry'],layer,lines)
    lines.extend(['0','ENDSEC','0','EOF'])
    return ('\r\n'.join(lines)+'\r\n').encode('ascii')


def _ifc_guid(seed: str) -> str:
    value = int.from_bytes(hashlib.md5(seed.encode('utf-8')).digest(), 'big')
    chars=[]
    for _ in range(22):
        chars.append(IFC64[value & 63]);value >>= 6
    return ''.join(reversed(chars))


def _ifc_string(value: str) -> str:
    return str(value).replace("'", "''")


def export_ifc(feature_collection: dict, project_name: str = 'LoteDiretor A.I TEC') -> bytes:
    export_geojson(feature_collection)
    entities=[]
    def add(text):entities.append(text);return len(entities)
    origin=add("IFCCARTESIANPOINT((0.,0.,0.))")
    axis=add(f"IFCAXIS2PLACEMENT3D(#{origin},$,$)")
    context=add(f"IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,#{axis},$)")
    unit=add("IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)")
    units=add(f"IFCUNITASSIGNMENT((#{unit}))")
    project=add(f"IFCPROJECT('{_ifc_guid(project_name+':project')}',$,'{_ifc_string(project_name)}',$,$,$,$,(#{context}),#{units})")
    site=add(f"IFCSITE('{_ifc_guid(project_name+':site')}',$,'Site',$,$,$,$,$,.ELEMENT.,$,$,$,$,$)")
    building=add(f"IFCBUILDING('{_ifc_guid(project_name+':building')}',$,'Building',$,$,$,$,$,.ELEMENT.,$,$,$)")
    add(f"IFCRELAGGREGATES('{_ifc_guid(project_name+':project-site')}',$,$,$,#{project},(#{site}))")
    add(f"IFCRELAGGREGATES('{_ifc_guid(project_name+':site-building')}',$,$,$,#{site},(#{building}))")
    products=[]
    for index, feature in enumerate(feature_collection['features']):
        geom=shape(feature['geometry'])
        if geom.is_empty:continue
        if geom.geom_type not in ('Polygon','LineString','Point'):
            parts=list(getattr(geom,'geoms',[]))
        else:parts=[geom]
        for pindex,part in enumerate(parts):
            if part.geom_type=='Polygon':coords=list(part.exterior.coords)
            elif part.geom_type=='LineString':coords=list(part.coords)
            elif part.geom_type=='Point':coords=[part.coords[0]]
            else:continue
            point_ids=[]
            for coord in coords:
                x,y=float(coord[0]),float(coord[1]);z=float(coord[2]) if len(coord)>2 else 0.0
                point_ids.append(add(f"IFCCARTESIANPOINT(({x:.6f},{y:.6f},{z:.6f}))"))
            curve=add(f"IFCPOLYLINE(({','.join('#'+str(pid) for pid in point_ids)}))")
            geomset=add(f"IFCGEOMETRICCURVESET((#{curve}))")
            rep=add(f"IFCSHAPEREPRESENTATION(#{context},'Body','GeometricCurveSet',(#{geomset}))")
            shape_id=add(f"IFCPRODUCTDEFINITIONSHAPE($,$,(#{rep}))")
            props=feature.get('properties') or {};name=_ifc_string(str(props.get('name') or f'Feature {index+1}.{pindex+1}'))
            product=add(f"IFCBUILDINGELEMENTPROXY('{_ifc_guid(project_name+':'+str(index)+':'+str(pindex))}',$,'{name}',$,$,$,#{shape_id},$,.NOTDEFINED.)")
            products.append(product)
    if products:add(f"IFCRELCONTAINEDINSPATIALSTRUCTURE('{_ifc_guid(project_name+':containment')}',$,$,$,({','.join('#'+str(x) for x in products)}),#{building})")
    body='\n'.join(f'#{i+1}={text};' for i,text in enumerate(entities))
    text="ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('ViewDefinition [ReferenceView]'),'2;1');\nFILE_NAME('lotediretor.ifc','2026-08-25T00:00:00',('LoteDiretor'),('LoteDiretor'),'LoteDiretor v20','LoteDiretor v20','');\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n"+body+"\nENDSEC;\nEND-ISO-10303-21;\n"
    return text.encode('utf-8')


def _xml(value: Any) -> str:
    return escape('' if value is None else str(value), quote=False)


def export_xlsx(sheets: dict[str, list[dict]]) -> bytes:
    if not sheets:raise ValueError('at least one XLSX sheet is required')
    names=[];sheet_xml=[]
    for index,(raw_name,rows) in enumerate(sheets.items(),start=1):
        name=re.sub(r'[\\/*?:\[\]]','_',str(raw_name))[:31] or f'Sheet{index}'
        names.append(name)
        headers=[]
        for row in rows:
            for key in row:
                if key not in headers:headers.append(key)
        matrix=[headers]+[[row.get(key) for key in headers] for row in rows]
        row_xml=[]
        for r,row in enumerate(matrix,start=1):
            cells=[]
            for c,value in enumerate(row,start=1):
                col='';n=c
                while n:
                    n,rem=divmod(n-1,26);col=chr(65+rem)+col
                ref=f'{col}{r}'
                if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(float(value)):
                    cells.append(f'<c r="{ref}"><v>{value}</v></c>')
                else:
                    cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{_xml(value)}</t></is></c>')
            row_xml.append(f'<row r="{r}">{"".join(cells)}</row>')
        sheet_xml.append('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(row_xml)+'</sheetData></worksheet>')
    workbook='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{escape(name,quote=True)}" sheetId="{i}" r:id="rId{i}"/>' for i,name in enumerate(names,start=1))+'</sheets></workbook>'
    wb_rels='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(names)+1))+'</Relationships>'
    root_rels='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    types='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(names)+1))+'</Types>'
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as z:
        entries={'[Content_Types].xml':types,'_rels/.rels':root_rels,'xl/workbook.xml':workbook,'xl/_rels/workbook.xml.rels':wb_rels}
        entries.update({f'xl/worksheets/sheet{i}.xml':xml for i,xml in enumerate(sheet_xml,start=1)})
        for path in sorted(entries):
            info=zipfile.ZipInfo(path,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,entries[path].encode('utf-8'))
    return buffer.getvalue()


def export_pdf(title: str, lines: list[str]) -> bytes:
    def clean(value):
        return str(value).encode('latin-1','replace').decode('latin-1').replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
    content=['BT','/F1 10 Tf','12 TL','50 790 Td',f'({clean(title)}) Tj','T*']
    for line in lines[:55]:content.extend([f'({clean(line)[:120]}) Tj','T*'])
    content.append('ET');stream='\n'.join(content).encode('latin-1')
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    data=bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n');offsets=[0]
    for index,obj in enumerate(objects,start=1):
        offsets.append(len(data));data.extend(f'{index} 0 obj\n'.encode());data.extend(obj);data.extend(b'\nendobj\n')
    xref=len(data);data.extend(f'xref\n0 {len(objects)+1}\n'.encode());data.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:data.extend(f'{offset:010d} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode());return bytes(data)


def export_gltf(feature_collection: dict, default_height_m: float = 3.0) -> bytes:
    export_geojson(feature_collection)
    positions=[];indices=[]
    def tri(a,b,c):
        base=len(positions);positions.extend([a,b,c]);indices.extend([base,base+1,base+2])
    def polygon_mesh(poly,height):
        if poly.is_empty:return
        for t in triangulate(poly):
            if not poly.covers(t.representative_point()):continue
            coords=list(t.exterior.coords)[:3]
            top=[(float(x),float(y),height) for x,y,*_ in coords];bottom=[(float(x),float(y),0.0) for x,y,*_ in coords]
            tri(*top);tri(bottom[2],bottom[1],bottom[0])
        ring=list(poly.exterior.coords)
        for a,b in zip(ring,ring[1:]):
            a0=(float(a[0]),float(a[1]),0.0);b0=(float(b[0]),float(b[1]),0.0);a1=(a0[0],a0[1],height);b1=(b0[0],b0[1],height)
            tri(a0,b0,b1);tri(a0,b1,a1)
    for feature in feature_collection['features']:
        geom=shape(feature['geometry']);height=float((feature.get('properties') or {}).get('height_m',default_height_m))
        if height<0:raise ValueError('glTF height must be >= 0')
        if geom.geom_type=='Polygon':polygon_mesh(geom,height)
        elif geom.geom_type=='MultiPolygon':
            for poly in geom.geoms:polygon_mesh(poly,height)
    if not positions:raise ValueError('glTF export requires Polygon/MultiPolygon features')
    pos_bytes=b''.join(struct.pack('<fff',*p) for p in positions);idx_bytes=b''.join(struct.pack('<I',i) for i in indices);padding=(4-len(pos_bytes)%4)%4;buffer=pos_bytes+b'\x00'*padding+idx_bytes
    flat=[v for p in positions for v in p];mins=[min(p[i] for p in positions) for i in range(3)];maxs=[max(p[i] for p in positions) for i in range(3)]
    gltf={'asset':{'version':'2.0','generator':'LoteDiretor A.I TEC v20'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'mesh':0}],'meshes':[{'primitives':[{'attributes':{'POSITION':0},'indices':1}]}],'buffers':[{'byteLength':len(buffer),'uri':'data:application/octet-stream;base64,'+base64.b64encode(buffer).decode('ascii')}],'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':len(pos_bytes),'target':34962},{'buffer':0,'byteOffset':len(pos_bytes)+padding,'byteLength':len(idx_bytes),'target':34963}],'accessors':[{'bufferView':0,'componentType':5126,'count':len(positions),'type':'VEC3','min':mins,'max':maxs},{'bufferView':1,'componentType':5125,'count':len(indices),'type':'SCALAR','min':[min(indices)],'max':[max(indices)]}]}
    return _canonical_json(gltf)


def export_manifest(files: dict[str, bytes]) -> dict[str, Any]:
    mime={'geojson':'application/geo+json','kml':'application/vnd.google-earth.kml+xml','kmz':'application/vnd.google-earth.kmz','dxf':'application/dxf','ifc':'application/x-step','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','pdf':'application/pdf','gltf':'model/gltf+json'}
    return {'version':EXPORT_VERSION,'files':{name:{'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'mime_type':mime.get(name.rsplit('.',1)[-1].lower(),'application/octet-stream')} for name,payload in sorted(files.items())}}
