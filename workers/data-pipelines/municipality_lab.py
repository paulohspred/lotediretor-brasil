from __future__ import annotations
import argparse, hashlib, json, os, sys
from pathlib import Path
from datetime import datetime, timezone
from connectors import fetch_feature_collection, s3_client, _quality

DB=os.getenv('PLATFORM_DATABASE_URL','')
S3_BUCKET=os.getenv('S3_BUCKET','lotediretor')

def _db_deps():
    if not DB:
        raise RuntimeError('PLATFORM_DATABASE_URL_required_for_db_command')
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError as exc:
        raise RuntimeError('psycopg_not_installed_for_db_command') from exc
    return psycopg, Jsonb



def load_profile(path:str)->dict:
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if not str(data.get('municipality_ibge','')).isdigit() or len(str(data['municipality_ibge']))!=7:
        raise RuntimeError('municipality_lab profile requires a 7 digit IBGE code')
    return data


def bootstrap(profile:dict)->dict:
    psycopg, Jsonb = _db_deps()
    ibge=profile['municipality_ibge']
    with psycopg.connect(DB) as c, c.transaction():
        c.execute("""insert into municipality.lab_profile(municipality_ibge,status,source_profile,validation_summary)
          values(%s,%s,%s,'{}'::jsonb) on conflict(municipality_ibge) do update set status=excluded.status,source_profile=excluded.source_profile,updated_at=now()""",
          (ibge,profile.get('status','DISCOVERED'),Jsonb(profile)))
        for src in profile.get('sources',[]):
            source_id=c.execute("""insert into source.registry(code,title,authority,access_class,channel,base_url,data_owner,cadence,health,license_terms,provenance)
              values(%s,%s,%s,'B',%s,%s,%s,'ON_DEMAND','UNKNOWN',%s,%s)
              on conflict(code) do update set authority=excluded.authority,channel=excluded.channel,base_url=excluded.base_url,provenance=excluded.provenance returning id""",
              (src['code'],src['code'],src['authority'],src['channel'],src['base_url'],src['authority'],src.get('license','REVIEW_REQUIRED'),Jsonb({'official':True,'municipality_ibge':ibge,'profile':'municipality_lab','license_url':src.get('license_url')}))).fetchone()[0]
            for ds in src.get('datasets',[]):
                c.execute("""insert into source.coverage(source_id,municipality_ibge,dataset_code,scope,availability_status,ingestion_status,access_class,metadata)
                  values(%s,%s,%s,'MUNICIPAL','DISCOVERED','NOT_INGESTED','B',%s)
                  on conflict(source_id,municipality_ibge,dataset_code) do update set metadata=excluded.metadata,updated_at=now()""",
                  (source_id,ibge,ds['code'],Jsonb(ds)))
    return {'status':'BOOTSTRAPPED','municipality_ibge':ibge}


def sync_wfs(profile:dict,source_code:str,dataset_code:str,typename:str,layer_code:str,domain:str,license_url:str,srs_name:str='EPSG:4326')->dict:
    psycopg, Jsonb = _db_deps()
    ibge=profile['municipality_ibge'];src=next((x for x in profile['sources'] if x['code']==source_code),None)
    if not src or src.get('channel')!='WFS': raise RuntimeError('profile source is not WFS')
    if not typename or not license_url: raise RuntimeError('typename and license_url are required before ingestion')
    spec={'code':source_code,'authority':src['authority'],'url':src['base_url'],'env':'MUNICIPALITY_LAB','mode':'WFS','typename':typename,'license_url':license_url,'srs_name':srs_name}
    payload,meta=fetch_feature_collection(spec)
    raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode();sha=hashlib.sha256(raw).hexdigest();checks=_quality(payload)
    blocking=sum(1 for q in checks if q['status']=='FAIL' and q['severity']=='ERROR')
    key=f"municipality/{ibge}/{dataset_code}/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{sha}.geojson"
    s3_client().put_object(Bucket=S3_BUCKET,Key=key,Body=raw,ContentType='application/geo+json',Metadata={'sha256':sha,'source':source_code,'municipality':ibge})
    with psycopg.connect(DB) as c, c.transaction():
        source_id=c.execute('select id from source.registry where code=%s',(source_code,)).fetchone()[0]
        snapshot_id=c.execute("""insert into source.snapshot(source_id,source_date,parser_version,sha256,object_key,metadata,status,quality,record_count,validation_status,schema_version)
          values(%s,now(),'municipality-wfs-v19',%s,%s,%s,%s,%s,%s,%s,'wfs-geojson-v1')
          on conflict(source_id,sha256) do update set object_key=excluded.object_key,metadata=excluded.metadata,quality=excluded.quality,record_count=excluded.record_count,validation_status=excluded.validation_status,status=excluded.status returning id""",
          (source_id,sha,key,Jsonb({'fetch':meta,'typename':typename,'dataset_code':dataset_code,'license_url':license_url,'srs_name':srs_name}), 'REJECTED' if blocking else 'VALIDATED',Jsonb({'checks':checks}),len(payload.get('features',[])),'FAIL' if blocking else 'PASS')).fetchone()[0]
        for q in checks:
            c.execute("""insert into data_quality.result(source_id,snapshot_id,check_code,severity,status,expected,observed) values(%s,%s,%s,%s,%s,%s,%s)
              on conflict(snapshot_id,check_code) do update set severity=excluded.severity,status=excluded.status,expected=excluded.expected,observed=excluded.observed,checked_at=now()""",
              (source_id,snapshot_id,q['code'],q['severity'],q['status'],Jsonb(q['expected']),Jsonb(q['observed'])))
        if blocking:
            c.execute("update source.coverage set ingestion_status='REJECTED',last_checked_at=now(),evidence_hash=%s where source_id=%s and municipality_ibge=%s and dataset_code=%s",(sha,source_id,ibge,dataset_code))
            return {'status':'REJECTED','snapshotId':str(snapshot_id),'blockingFailures':blocking}
        layer_id=c.execute("""insert into geo.layer(code,title,domain,municipality_ibge,source_id,dataset_code,geometry_type,visibility,status,metadata)
          values(%s,%s,%s,%s,%s,%s,'GEOMETRY','PUBLIC','ACTIVE',%s)
          on conflict(code) do update set source_id=excluded.source_id,dataset_code=excluded.dataset_code,status='ACTIVE',metadata=excluded.metadata,updated_at=now() returning id""",
          (layer_code,layer_code,domain.upper(),ibge,source_id,dataset_code,Jsonb({'typename':typename,'license_url':license_url,'srs_name':srs_name}))).fetchone()[0]
        c.execute('delete from geo.feature where layer_id=%s and source_snapshot_id=%s',(layer_id,snapshot_id))
        loaded=0
        for f in payload.get('features',[]):
            if not f.get('geometry'): continue
            props=f.get('properties') or {};fid=f.get('id') or props.get('id') or props.get('codigo') or props.get('code')
            c.execute("""insert into geo.feature(layer_id,tenant_id,source_snapshot_id,official_identifier,geom,attributes)
              values(%s,null,%s,%s,st_setsrid(st_geomfromgeojson(%s),4326),%s)""",(layer_id,snapshot_id,str(fid) if fid is not None else None,json.dumps(f['geometry']),Jsonb(props)));loaded+=1
        previous=c.execute("select snapshot_id from source.publication where source_id=%s and municipality_ibge=%s and (dataset_code=%s or dataset_code is null) and status='ACTIVE' for update",(source_id,ibge,dataset_code)).fetchone()
        c.execute("update source.publication set status='INACTIVE',deactivated_at=now() where source_id=%s and municipality_ibge=%s and (dataset_code=%s or dataset_code is null) and status='ACTIVE'",(source_id,ibge,dataset_code))
        c.execute("insert into source.publication(source_id,municipality_ibge,dataset_code,snapshot_id,status) values(%s,%s,%s,%s,'ACTIVE')",(source_id,ibge,dataset_code,snapshot_id))
        c.execute("update source.snapshot set status='PUBLISHED',published_at=coalesce(published_at,now()) where id=%s",(snapshot_id,))
        c.execute("""update source.coverage set availability_status='AVAILABLE',ingestion_status='PUBLISHED',parser_version='municipality-wfs-v19',last_checked_at=now(),last_source_update=now(),evidence_hash=%s,metadata=metadata||%s where source_id=%s and municipality_ibge=%s and dataset_code=%s""",(sha,Jsonb({'typename':typename,'layer_code':layer_code,'license_url':license_url,'srs_name':srs_name}),source_id,ibge,dataset_code))
        c.execute("insert into source.publication_event(source_id,municipality_ibge,dataset_code,previous_snapshot_id,next_snapshot_id,action,actor,reason) values(%s,%s,%s,%s,%s,'ACTIVATE','municipality-lab','WFS layer passed v19 quality gate')",(source_id,ibge,dataset_code,previous[0] if previous else None,snapshot_id))
    return {'status':'PUBLISHED','municipality_ibge':ibge,'dataset':dataset_code,'snapshotId':str(snapshot_id),'layerId':str(layer_id),'sha256':sha,'received':len(payload.get('features',[])),'loaded':loaded}



def _active_snapshot_for_layer(c, municipality_ibge:str, layer_code:str):
    row=c.execute("""select l.id,l.source_id,l.dataset_code,p.snapshot_id
      from geo.layer l join source.publication p on p.source_id=l.source_id and p.municipality_ibge=l.municipality_ibge and p.dataset_code=l.dataset_code and p.status='ACTIVE'
      where l.code=%s and l.municipality_ibge=%s and l.status='ACTIVE'""",(layer_code,municipality_ibge)).fetchone()
    if not row:raise RuntimeError(f'active published layer not found: {layer_code}/{municipality_ibge}')
    return row


def promote_parcels(profile:dict,layer_code:str,id_field:str|None=None,valid_from:str|None=None)->dict:
    psycopg, Jsonb = _db_deps()
    """Promote a QA-published generic WFS layer into the canonical parcel table.

    Attribute mapping is explicit. If id_field is omitted, only the generic WFS feature
    identifier captured during ingestion is used. Existing active parcel versions are
    closed instead of deleted so historical analyses remain reproducible.
    """
    ibge=profile['municipality_ibge']
    with psycopg.connect(DB) as c, c.transaction():
        layer_id,source_id,dataset_code,snapshot_id=_active_snapshot_for_layer(c,ibge,layer_code)
        # Do not silently duplicate the same snapshot.
        existing=c.execute('select count(*) from geo.parcel where municipality_ibge=%s and source_snapshot_id=%s',(ibge,snapshot_id)).fetchone()[0]
        if existing:
            return {'status':'ALREADY_PROMOTED','municipality_ibge':ibge,'layerCode':layer_code,'snapshotId':str(snapshot_id),'parcels':existing}
        vf=valid_from or datetime.now(timezone.utc).isoformat()
        c.execute("""update geo.parcel set valid_to=%s::timestamptz,superseded_at=now()
          where municipality_ibge=%s and valid_to is null and source_snapshot_id<>%s""",(vf,ibge,snapshot_id))
        r=c.execute("""insert into geo.parcel(tenant_id,municipality_ibge,source_snapshot_id,official_identifier,geom,valid_from)
          select null,%s,%s,coalesce(case when %s is null then null else nullif(attributes->>%s,'') end,official_identifier),
                 st_multi(st_collectionextract(st_makevalid(geom),3)),%s::timestamptz
          from geo.feature where layer_id=%s and source_snapshot_id=%s and geom is not null
            and not st_isempty(st_collectionextract(st_makevalid(geom),3))
          returning id""",(ibge,snapshot_id,id_field,id_field,vf,layer_id,snapshot_id))
        count=len(r.fetchall())
        if not count:raise RuntimeError('parcel promotion produced zero polygon features')
        c.execute("""update source.coverage set metadata=metadata||%s,updated_at=now()
          where source_id=%s and municipality_ibge=%s and dataset_code=%s""",
          (Jsonb({'domain_promotion':{'target':'geo.parcel','snapshot_id':str(snapshot_id),'id_field':id_field,'promoted_at':datetime.now(timezone.utc).isoformat(),'count':count}}),source_id,ibge,dataset_code))
    return {'status':'PROMOTED','municipality_ibge':ibge,'target':'geo.parcel','snapshotId':str(snapshot_id),'parcels':count,'idField':id_field}


def promote_zones(profile:dict,layer_code:str,code_field:str,name_field:str|None,valid_from:str,valid_to:str|None=None)->dict:
    psycopg, Jsonb = _db_deps()
    """Promote a QA-published generic WFS layer into canonical planning.zone.

    The legal valid_from date and exact source attribute containing the zone code are
    mandatory; the command refuses to infer either one.
    """
    if not code_field:raise RuntimeError('zone code_field is required; inspect the WFS schema first')
    if not valid_from:raise RuntimeError('zone valid_from is required; do not infer legal vigency from ingestion time')
    ibge=profile['municipality_ibge']
    with psycopg.connect(DB) as c, c.transaction():
        layer_id,source_id,dataset_code,snapshot_id=_active_snapshot_for_layer(c,ibge,layer_code)
        existing=c.execute('select count(*) from planning.zone where municipality_ibge=%s and source_snapshot_id=%s',(ibge,snapshot_id)).fetchone()[0]
        if existing:
            return {'status':'ALREADY_PROMOTED','municipality_ibge':ibge,'layerCode':layer_code,'snapshotId':str(snapshot_id),'zones':existing}
        # A new homologated legal geometry supersedes older open-ended zone geometries at the supplied legal date.
        c.execute("""update planning.zone set valid_to=%s::timestamptz
          where municipality_ibge=%s and valid_to is null and source_snapshot_id<>%s""",(valid_from,ibge,snapshot_id))
        missing=c.execute("""select count(*) filter(where coalesce(nullif(attributes->>%s,''),'')=''),array_agg(coalesce(official_identifier,id::text) order by id) filter(where coalesce(nullif(attributes->>%s,''),'')='')
          from geo.feature where layer_id=%s and source_snapshot_id=%s and geom is not null""",(code_field,code_field,layer_id,snapshot_id)).fetchone()
        if missing and missing[0]:raise RuntimeError(f'zone promotion aborted: {missing[0]} feature(s) missing required attribute {code_field}; examples={(missing[1] or [])[:10]}')
        # Dissolve fragmented WFS features into one canonical MultiPolygon per zone code.
        r=c.execute("""insert into planning.zone(municipality_ibge,code,name,geom,source_snapshot_id,valid_from,valid_to)
          select %s,nullif(attributes->>%s,''),case when %s is null then null else max(nullif(attributes->>%s,'')) end,
                 st_multi(st_unaryunion(st_collect(st_collectionextract(st_makevalid(geom),3)))),%s,%s::timestamptz,%s::timestamptz
          from geo.feature where layer_id=%s and source_snapshot_id=%s and geom is not null
            and not st_isempty(st_collectionextract(st_makevalid(geom),3))
          group by nullif(attributes->>%s,'') returning id""",
          (ibge,code_field,name_field,name_field,snapshot_id,valid_from,valid_to,layer_id,snapshot_id,code_field))
        loaded=len(r.fetchall())
        if not loaded:raise RuntimeError('zone promotion produced zero polygon groups')
        c.execute("""update source.coverage set metadata=metadata||%s,updated_at=now()
          where source_id=%s and municipality_ibge=%s and dataset_code=%s""",
          (Jsonb({'domain_promotion':{'target':'planning.zone','snapshot_id':str(snapshot_id),'code_field':code_field,'name_field':name_field,'valid_from':valid_from,'valid_to':valid_to,'promoted_at':datetime.now(timezone.utc).isoformat(),'count':loaded}}),source_id,ibge,dataset_code))
    return {'status':'PROMOTED','municipality_ibge':ibge,'target':'planning.zone','snapshotId':str(snapshot_id),'zones':loaded,'codeField':code_field,'nameField':name_field,'validFrom':valid_from,'validTo':valid_to}


def inspect_wfs(profile:dict,source_code:str,typename:str,srs_name:str='EPSG:4326')->dict:
    src=next((x for x in profile['sources'] if x['code']==source_code),None)
    if not src or src.get('channel')!='WFS':raise RuntimeError('profile source is not WFS')
    spec={'code':source_code,'authority':src['authority'],'url':src['base_url'],'env':'MUNICIPALITY_LAB','mode':'WFS','typename':typename,'license_url':src.get('license_url','inspection-only'),'srs_name':srs_name}
    old_pages=os.environ.get(f'{source_code}_SOURCE_MAX_PAGES');old_size=os.environ.get(f'{source_code}_SOURCE_PAGE_SIZE')
    os.environ[f'{source_code}_SOURCE_MAX_PAGES']='1';os.environ[f'{source_code}_SOURCE_PAGE_SIZE']='5'
    try:payload,meta=fetch_feature_collection(spec)
    finally:
        if old_pages is None:os.environ.pop(f'{source_code}_SOURCE_MAX_PAGES',None)
        else:os.environ[f'{source_code}_SOURCE_MAX_PAGES']=old_pages
        if old_size is None:os.environ.pop(f'{source_code}_SOURCE_PAGE_SIZE',None)
        else:os.environ[f'{source_code}_SOURCE_PAGE_SIZE']=old_size
    features=payload.get('features',[]);keys=sorted({str(k) for f in features for k in (f.get('properties') or {}).keys()})
    sample=[]
    for f in features[:3]:sample.append({'id':f.get('id'),'geometry_type':(f.get('geometry') or {}).get('type'),'properties':f.get('properties') or {}})
    return {'status':'INSPECTED','typename':typename,'srs_name':srs_name,'property_keys':keys,'sample':sample,'fetch':meta}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--profile',required=True);sub=ap.add_subparsers(dest='cmd',required=True)
    sub.add_parser('bootstrap')
    w=sub.add_parser('sync-wfs');w.add_argument('--source',required=True);w.add_argument('--dataset',required=True);w.add_argument('--typename',required=True);w.add_argument('--layer-code',required=True);w.add_argument('--domain',required=True);w.add_argument('--license-url',required=True);w.add_argument('--srs-name',default='EPSG:4326')
    i=sub.add_parser('inspect-wfs');i.add_argument('--source',required=True);i.add_argument('--typename',required=True);i.add_argument('--srs-name',default='EPSG:4326')
    pp=sub.add_parser('promote-parcels');pp.add_argument('--layer-code',required=True);pp.add_argument('--id-field');pp.add_argument('--valid-from')
    pz=sub.add_parser('promote-zones');pz.add_argument('--layer-code',required=True);pz.add_argument('--code-field',required=True);pz.add_argument('--name-field');pz.add_argument('--valid-from',required=True);pz.add_argument('--valid-to')
    args=ap.parse_args();profile=load_profile(args.profile)
    try:
        if args.cmd=='bootstrap':result=bootstrap(profile)
        elif args.cmd=='inspect-wfs':result=inspect_wfs(profile,args.source,args.typename,args.srs_name)
        elif args.cmd=='promote-parcels':result=promote_parcels(profile,args.layer_code,args.id_field,args.valid_from)
        elif args.cmd=='promote-zones':result=promote_zones(profile,args.layer_code,args.code_field,args.name_field,args.valid_from,args.valid_to)
        else:result=sync_wfs(profile,args.source,args.dataset,args.typename,args.layer_code,args.domain,args.license_url,args.srs_name)
    except Exception as exc:
        print(json.dumps({'status':'ERROR','command':args.cmd,'error':str(exc)},ensure_ascii=False,indent=2),file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
