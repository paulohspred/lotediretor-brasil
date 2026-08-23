from __future__ import annotations
import io, zipfile
from html import escape

def coords_from_geojson(g):
    if not g:return []
    t=g.get('type'); c=g.get('coordinates') or []
    if t=='Polygon':return c
    if t=='MultiPolygon':return [ring for poly in c for ring in poly]
    return []

def placemark(name,geom,description=''):
    rings=coords_from_geojson(geom); out=[]
    for ring in rings:
        coords=' '.join(f'{float(p[0])},{float(p[1])},0' for p in ring)
        out.append(f'<Placemark><name>{escape(name)}</name><description>{escape(description)}</description><Polygon><outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
    return ''.join(out)

def kml_document(asset,records):
    parts=['<?xml version="1.0" encoding="UTF-8"?>','<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',f'<name>{escape(asset.get("name") or "RE Rural")}</name>',placemark('Ativo interno — referência física',asset.get('geometry'),'Não substitui CAR, SIGEF, SNCR, CIB ou matrícula.')]
    for r in records:
        if r.get('geometry'):parts.append(placemark(f'{r["registry_type"]} · {r.get("official_identifier") or "sem identificador"}',r['geometry'],'Registro preservado como fonte independente.'))
    parts.append('</Document></kml>');return ''.join(parts).encode('utf-8')

def package_export(kml:bytes,fmt:str):
    if fmt=='KMZ':
        bio=io.BytesIO()
        with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('doc.kml',kml)
        return bio.getvalue(),'kmz','application/vnd.google-earth.kmz'
    return kml,'kml','application/vnd.google-earth.kml+xml'
