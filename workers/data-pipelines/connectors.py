from __future__ import annotations
import hashlib, json, os, subprocess, tempfile, zipfile
from datetime import datetime, timezone
from typing import Any
try:
    import boto3
    from botocore.config import Config
except ModuleNotFoundError:
    boto3=None; Config=None
try:
    import psycopg
    from psycopg.types.json import Jsonb
except ModuleNotFoundError:
    psycopg=None
    class Jsonb:
        def __init__(self,value): self.value=value
try:
    import requests
except ModuleNotFoundError:
    requests=None

DB=os.getenv('PLATFORM_DATABASE_URL','')
S3_BUCKET=os.getenv('S3_BUCKET','lotediretor')


def s3_client():
    if boto3 is None: raise RuntimeError('boto3_not_installed')
    return boto3.client('s3',endpoint_url=os.getenv('S3_ENDPOINT','http://minio:9000'),aws_access_key_id=os.getenv('S3_ACCESS_KEY','lotediretor'),aws_secret_access_key=os.getenv('S3_SECRET_KEY','lotediretor-local-secret'),region_name=os.getenv('S3_REGION','us-east-1'),config=Config(signature_version='s3v4'))


def configured_geojson_sources()->list[dict[str,str]]:
    """Return only geospatial adapters whose endpoint was explicitly enabled.

    Source discovery is not activation. Known transport modes are pinned here so an
    operator cannot accidentally treat an official SHP/CKAN or WFS service as raw
    GeoJSON. SIGEF is intentionally excluded because its Conecta contract is not a
    generic FeatureCollection feed.
    """
    specs=[]
    definitions=[
        ('CAR','SICAR / órgão ambiental competente','CAR_SOURCE_URL','GEOJSON'),
        ('IBAMA_EMBARGO','IBAMA','IBAMA_EMBARGO_SOURCE_URL','CKAN_SHP_ZIP_GDAL'),
        ('PRODES','INPE / TerraBrasilis','PRODES_SOURCE_URL','WFS'),
    ]
    for code,authority,env,default_mode in definitions:
        url=os.getenv(env,'').strip();enabled=os.getenv(f'{code}_SOURCE_ENABLED','false').strip().lower() in {'1','true','yes'}
        if not url or not enabled: continue
        specs.append({
            'code':code,'authority':authority,'url':url,'env':env,
            'mode':os.getenv(f'{code}_SOURCE_MODE',default_mode).strip().upper() or default_mode,
            'typename':os.getenv(f'{code}_SOURCE_TYPENAME','').strip(),
            'license_url':os.getenv(f'{code}_SOURCE_LICENSE_URL','').strip(),
            'srs_name':os.getenv(f'{code}_SOURCE_SRS_NAME','EPSG:4326').strip() or 'EPSG:4326',
        })
    return specs


def _quality(payload:Any)->list[dict]:
    checks=[]
    def add(code,status,expected,observed,severity='ERROR'):checks.append({'code':code,'status':status,'severity':severity,'expected':expected,'observed':observed})
    is_fc=isinstance(payload,dict) and payload.get('type')=='FeatureCollection' and isinstance(payload.get('features'),list)
    add('geojson_feature_collection','PASS' if is_fc else 'FAIL',{'type':'FeatureCollection'},{'type':payload.get('type') if isinstance(payload,dict) else type(payload).__name__})
    if not is_fc:return checks
    features=payload['features'];add('feature_count','PASS' if len(features)>0 else 'FAIL',{'min':1},{'count':len(features)})
    with_geometry=sum(1 for f in features if isinstance(f,dict) and isinstance(f.get('geometry'),dict) and f['geometry'].get('type'))
    add('geometry_presence','PASS' if with_geometry==len(features) else 'FAIL',{'with_geometry':len(features)},{'with_geometry':with_geometry,'total':len(features)})
    ids=[str(f.get('id')) for f in features if isinstance(f,dict) and f.get('id') is not None]
    add('feature_id_uniqueness','PASS' if len(ids)==len(set(ids)) else 'FAIL',{'duplicates':0},{'duplicates':len(ids)-len(set(ids))},'WARN')
    def points(coords):
        if isinstance(coords,(list,tuple)) and len(coords)>=2 and all(isinstance(x,(int,float)) for x in coords[:2]):
            yield float(coords[0]),float(coords[1]);return
        if isinstance(coords,(list,tuple)):
            for item in coords: yield from points(item)
    sampled=[]
    for f in features[:500]:
        g=f.get('geometry') if isinstance(f,dict) else None
        if not isinstance(g,dict):continue
        for xy in points(g.get('coordinates')):
            sampled.append(xy)
            if len(sampled)>=5000:break
        if len(sampled)>=5000:break
    in_range=sum(1 for x,y in sampled if -180<=x<=180 and -90<=y<=90)
    add('epsg4326_coordinate_range','PASS' if sampled and in_range==len(sampled) else 'FAIL',{'all_sampled_coordinates':'lon[-180,180],lat[-90,90]'},{'sampled':len(sampled),'in_range':in_range},'ERROR')
    return checks


def _headers(code:str)->dict[str,str]:
    h={'accept':'application/geo+json,application/json','user-agent':'LoteDiretor/19.0.0-rc.3'}
    bearer=os.getenv(f'{code}_SOURCE_BEARER','').strip()
    if bearer:h['authorization']=f'Bearer {bearer}'
    return h


def _ckan_shp_resource(package_payload:dict)->str:
    result=package_payload.get('result') if isinstance(package_payload,dict) else None
    resources=(result or {}).get('resources') or []
    candidates=[]
    for r in resources:
        fmt=str(r.get('format') or '').upper().replace('_','-')
        name=str(r.get('name') or '').lower()
        url=str(r.get('url') or '').strip()
        if url and ('SHP' in fmt or url.lower().endswith('.zip')):
            candidates.append((0 if ('pol' in name or 'área' in name or 'area' in name) else 1,url))
    if not candidates: raise RuntimeError('CKAN package has no SHP-ZIP resource')
    return sorted(candidates)[0][1]


def _fetch_ckan_shp_zip(spec:dict[str,str],session)->tuple[dict[str,Any],dict[str,Any]]:
    code=spec['code']
    meta=session.get(spec['url'],headers=_headers(code),timeout=90);meta.raise_for_status()
    resource_url=_ckan_shp_resource(meta.json())
    r=session.get(resource_url,headers=_headers(code),timeout=300);r.raise_for_status()
    with tempfile.TemporaryDirectory(prefix='ld-ckan-') as td:
        zpath=os.path.join(td,'source.zip')
        with open(zpath,'wb') as fh: fh.write(r.content)
        with zipfile.ZipFile(zpath) as z: z.extractall(os.path.join(td,'src'))
        shp=[]
        for base,_,files in os.walk(os.path.join(td,'src')):
            shp.extend(os.path.join(base,f) for f in files if f.lower().endswith('.shp'))
        if not shp: raise RuntimeError(f'{code}: SHP-ZIP contains no .shp file')
        out=os.path.join(td,'out.geojson')
        proc=subprocess.run(['ogr2ogr','-t_srs','EPSG:4326','-f','GeoJSON',out,shp[0]],capture_output=True,text=True,timeout=600)
        if proc.returncode!=0: raise RuntimeError(f'{code}: ogr2ogr failed: {proc.stderr[-1000:]}')
        with open(out,encoding='utf-8') as fh: payload=json.load(fh)
    return payload,{'http_status':r.status_code,'mode':'CKAN_SHP_ZIP_GDAL','pages':1,'package_url':spec['url'],'resource_url':resource_url}


def fetch_feature_collection(spec:dict[str,str], session:requests.Session|None=None)->tuple[dict[str,Any],dict[str,Any]]:
    """Fetch a configured source without silently changing its semantics.

    Modes:
      GEOJSON: endpoint already returns a FeatureCollection.
      WFS: WFS 2.0 GetFeature with outputFormat=application/json and startIndex/count paging.
      ARCGIS_GEOJSON: ArcGIS FeatureServer query endpoint with f=geojson paging.
    """
    if session is None and requests is None: raise RuntimeError('requests_not_installed')
    s=session or requests.Session();code=spec['code'];mode=spec.get('mode','GEOJSON').upper();url=spec['url'];headers=_headers(code)
    if mode=='CKAN_SHP_ZIP_GDAL': return _fetch_ckan_shp_zip(spec,s)
    page_size=max(1,min(int(os.getenv(f'{code}_SOURCE_PAGE_SIZE','2000')),10000));max_pages=max(1,min(int(os.getenv(f'{code}_SOURCE_MAX_PAGES','500')),5000))
    if mode=='GEOJSON':
        r=s.get(url,headers=headers,timeout=120);r.raise_for_status();payload=r.json()
        return payload,{'http_status':r.status_code,'mode':mode,'pages':1,'url':r.url}
    features=[];seen=set();last_url=url
    for page in range(max_pages):
        offset=page*page_size
        if mode=='WFS':
            typename=spec.get('typename') or ''
            if not typename:raise RuntimeError(f'{code}: SOURCE_TYPENAME is required for WFS mode')
            params={'service':'WFS','request':'GetFeature','version':spec.get('wfs_version','2.0.0'),'outputFormat':'application/json','typeNames':typename,'count':page_size,'startIndex':offset};srs_name=spec.get('srs_name') or '';params.update({'srsName':srs_name} if srs_name else {})
        elif mode=='ARCGIS_GEOJSON':
            params={'where':'1=1','outFields':'*','returnGeometry':'true','f':'geojson','resultOffset':offset,'resultRecordCount':page_size,'orderByFields':'OBJECTID'}
        else:raise RuntimeError(f'{code}: unsupported source mode {mode}')
        r=s.get(url,headers=headers,params=params,timeout=180);r.raise_for_status();last_url=r.url;payload=r.json()
        if not isinstance(payload,dict) or payload.get('type')!='FeatureCollection' or not isinstance(payload.get('features'),list):raise RuntimeError(f'{code}: {mode} did not return GeoJSON FeatureCollection')
        page_features=payload['features']
        for f in page_features:
            marker=f.get('id') if isinstance(f,dict) else None
            if marker is None:features.append(f);continue
            key=str(marker)
            if key not in seen:seen.add(key);features.append(f)
        if len(page_features)<page_size:break
    else:raise RuntimeError(f'{code}: pagination reached SOURCE_MAX_PAGES={max_pages}; refuse partial publication')
    return {'type':'FeatureCollection','features':features},{'http_status':200,'mode':mode,'pages':page+1,'url':last_url}


def sync_geojson_source(spec:dict[str,str])->dict:
    code,authority,url=spec['code'],spec['authority'],spec['url']
    payload,fetch_meta=fetch_feature_collection(spec)
    raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    checks=_quality(payload);blocking=sum(1 for q in checks if q['status']=='FAIL' and q['severity']=='ERROR')
    sha=hashlib.sha256(raw).hexdigest();validation='FAIL' if blocking else 'PASS';features=payload.get('features',[]) if isinstance(payload,dict) else []
    key=f"source/{code}/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{sha}.geojson"
    s3_client().put_object(Bucket=S3_BUCKET,Key=key,Body=raw,ContentType='application/geo+json',Metadata={'sha256':sha,'source':code})
    if not spec.get('license_url'): raise RuntimeError(f'{code}: license/access terms URL is required before publication')
    provenance={'configured_by_env':spec['env'],'official_endpoint_verified_by_operator':True,'mode':spec.get('mode','GEOJSON'),'license_url':spec.get('license_url')}
    if psycopg is None: raise RuntimeError('psycopg_not_installed')
    if not DB: raise RuntimeError('PLATFORM_DATABASE_URL_required')
    with psycopg.connect(DB) as c:
      with c.transaction():
        src=c.execute("""insert into source.registry(code,title,authority,access_class,channel,base_url,data_owner,cadence,health,provenance)
          values(%s,%s,%s,'B','REST',%s,%s,'ON_DEMAND','OK',%s)
          on conflict(code) do update set title=excluded.title,authority=excluded.authority,base_url=excluded.base_url,data_owner=excluded.data_owner,health=excluded.health,provenance=excluded.provenance returning id""",
          (code,code,authority,url,authority,Jsonb(provenance))).fetchone()[0]
        c.execute("""insert into source.dataset_contract(source_id,version,required_fields,geometry_type,srid,primary_keys,freshness_hours,license_required,status)
          values(%s,'geojson-featurecollection-v2','[\"type\",\"features\"]'::jsonb,'Geometry',4326,ARRAY[]::text[],null,true,'ACTIVE')
          on conflict(source_id,version) do update set status='ACTIVE'""",(src,))
        snap=c.execute("""insert into source.snapshot(source_id,source_date,parser_version,sha256,object_key,metadata,status,quality,record_count,validation_status,schema_version)
          values(%s,now(),'generic-geojson-v2',%s,%s,%s,%s,%s,%s,%s,'geojson-featurecollection-v2')
          on conflict(source_id,sha256) do update set object_key=excluded.object_key,metadata=excluded.metadata,status=excluded.status,quality=excluded.quality,record_count=excluded.record_count,validation_status=excluded.validation_status returning id""",
          (src,sha,key,Jsonb(fetch_meta), 'VALIDATED' if validation=='PASS' else 'REJECTED',Jsonb({'checks':checks}),len(features),validation)).fetchone()[0]
        for q in checks:
          c.execute("""insert into data_quality.result(source_id,snapshot_id,check_code,severity,status,expected,observed) values(%s,%s,%s,%s,%s,%s,%s)
            on conflict(snapshot_id,check_code) do update set severity=excluded.severity,status=excluded.status,expected=excluded.expected,observed=excluded.observed,checked_at=now()""",(src,snap,q['code'],q['severity'],q['status'],Jsonb(q['expected']),Jsonb(q['observed'])))
        if validation!='PASS':
          c.execute("update source.registry set health='DEGRADED' where id=%s",(src,));return {'source':code,'status':'REJECTED','snapshotId':str(snap),'blockingFailures':blocking}
        c.execute("delete from rural.layer_feature where layer_code=%s and source_snapshot_id=%s",(code,snap))
        loaded=0
        for f in features:
          geom=f.get('geometry');props=f.get('properties') or {};fid=f.get('id') or props.get('id') or props.get('codigo') or props.get('code')
          if not geom:continue
          try:
            c.execute("""insert into rural.layer_feature(layer_code,source_snapshot_id,official_identifier,geom,attributes)
              values(%s,%s,%s,st_setsrid(st_geomfromgeojson(%s),4326),%s)""",(code,snap,str(fid) if fid is not None else None,json.dumps(geom),Jsonb(props)));loaded+=1
          except Exception as exc:raise RuntimeError(f'{code}: feature {loaded} failed geometry load: {exc}') from exc
        previous=c.execute("select snapshot_id from source.publication where source_id=%s and municipality_ibge is null and (dataset_code=%s or dataset_code is null) and status='ACTIVE' for update",(src,code)).fetchone()
        c.execute("update source.publication set status='INACTIVE',deactivated_at=now() where source_id=%s and municipality_ibge is null and (dataset_code=%s or dataset_code is null) and status='ACTIVE'",(src,code))
        c.execute("insert into source.publication(source_id,municipality_ibge,dataset_code,snapshot_id,status) values(%s,null,%s,%s,'ACTIVE')",(src,code,snap))
        c.execute("update source.snapshot set status='PUBLISHED',published_at=coalesce(published_at,now()) where id=%s",(snap,))
        c.execute("update rural.layer_catalog set status='ACTIVE',metadata=metadata||%s where code=%s",(Jsonb({'last_snapshot_id':str(snap),'configured_url_env':spec['env'],'source_mode':spec.get('mode','GEOJSON')}),code))
        c.execute("insert into source.publication_event(source_id,dataset_code,previous_snapshot_id,next_snapshot_id,action,actor,reason) values(%s,%s,%s,%s,'ACTIVATE','data-pipelines','configured geospatial connector activation after PASS quality checks')",(src,code,previous[0] if previous else None,snap))
    return {'source':code,'status':'PUBLISHED','snapshotId':str(snap),'sha256':sha,'received':len(features),'loaded':loaded,'mode':spec.get('mode','GEOJSON'),'pages':fetch_meta.get('pages')}
