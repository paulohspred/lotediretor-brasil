from __future__ import annotations
import hashlib,json,os,time
from datetime import datetime,timezone
import requests,psycopg,boto3
from botocore.config import Config
from psycopg.types.json import Jsonb
from connectors import configured_geojson_sources,sync_geojson_source

DB=os.environ['PLATFORM_DATABASE_URL']
IBGE_URL='https://servicodados.ibge.gov.br/api/v1/localidades/municipios?orderBy=nome'
INTERVAL=int(os.getenv('IBGE_SYNC_INTERVAL_SECONDS','86400'))
S3_BUCKET=os.getenv('S3_BUCKET','lotediretor')


def s3_client():
    return boto3.client(
        's3',endpoint_url=os.getenv('S3_ENDPOINT','http://minio:9000'),
        aws_access_key_id=os.getenv('S3_ACCESS_KEY','lotediretor'),
        aws_secret_access_key=os.getenv('S3_SECRET_KEY','lotediretor-local-secret'),
        region_name=os.getenv('S3_REGION','us-east-1'),config=Config(signature_version='s3v4')
    )


def extract_uf(m:dict):
    micro=((m.get('microrregiao') or {}).get('mesorregiao') or {}).get('UF') or {}
    immediate=m.get('regiao-imediata') or m.get('regiao_imediata') or {}
    intermediate=immediate.get('regiao-intermediaria') or immediate.get('regiao_intermediaria') or {}
    return micro or intermediate.get('UF') or {}


def validate(data):
    checks=[]
    def add(code,severity,status,expected,observed):checks.append({'code':code,'severity':severity,'status':status,'expected':expected,'observed':observed})
    add('payload_array','ERROR','PASS' if isinstance(data,list) else 'FAIL',{'type':'array'},{'type':type(data).__name__})
    if not isinstance(data,list):return checks
    count=len(data);add('municipality_count','ERROR','PASS' if 5500<=count<=5700 else 'FAIL',{'min':5500,'max':5700},{'count':count})
    codes=[str(x.get('id','')) for x in data];valid=sum(1 for x in codes if len(x)==7 and x.isdigit());add('ibge_code_format','ERROR','PASS' if valid==count else 'FAIL',{'valid':count},{'valid':valid,'total':count})
    duplicates=len(codes)-len(set(codes));add('ibge_code_unique','ERROR','PASS' if duplicates==0 else 'FAIL',{'duplicates':0},{'duplicates':duplicates})
    with_uf=sum(1 for m in data if str(extract_uf(m).get('sigla','')).strip());add('uf_presence','ERROR','PASS' if with_uf==count else 'FAIL',{'with_uf':count},{'with_uf':with_uf,'total':count})
    return checks


def sync_ibge():
    response=requests.get(IBGE_URL,headers={'accept':'application/json','user-agent':'LoteDiretor/17.0'},timeout=90)
    response.raise_for_status();raw=response.content;data=response.json();sha=hashlib.sha256(raw).hexdigest();checks=validate(data)
    blocking=sum(1 for x in checks if x['status']=='FAIL' and x['severity']=='ERROR');validation='FAIL' if blocking else 'PASS'
    key=f"source/IBGE_LOCALIDADES/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{sha}.json"
    try:s3_client().put_object(Bucket=S3_BUCKET,Key=key,Body=raw,ContentType='application/json',Metadata={'sha256':sha,'source':'IBGE_LOCALIDADES'})
    except Exception as exc:raise RuntimeError(f'raw snapshot storage failed: {exc}') from exc
    with psycopg.connect(DB) as c:
      with c.transaction():
        src=c.execute("""insert into source.registry(code,title,authority,access_class,channel,base_url,data_owner,cadence,health,provenance)
          values('IBGE_LOCALIDADES','IBGE Localidades — Municípios','Instituto Brasileiro de Geografia e Estatística','A','REST',%s,'IBGE','DAILY','OK','{"official":true,"purpose":"municipality_catalog"}'::jsonb)
          on conflict(code) do update set health='OK',base_url=excluded.base_url,cadence='DAILY' returning id""",(IBGE_URL,)).fetchone()[0]
        c.execute("""insert into source.dataset_contract(source_id,version,required_fields,primary_keys,freshness_hours,license_required,status)
          values(%s,'ibge-municipalities-v1','["id","nome"]'::jsonb,ARRAY['id'],48,false,'ACTIVE')
          on conflict(source_id,version) do update set freshness_hours=excluded.freshness_hours,status='ACTIVE'""",(src,))
        snap=c.execute("""insert into source.snapshot(source_id,source_date,parser_version,sha256,object_key,metadata,status,quality,published_at,record_count,validation_status,schema_version)
          values(%s,now(),'ibge-municipalities-v3',%s,%s,%s,%s,%s,null,%s,%s,'ibge-localidades-v1')
          on conflict(source_id,sha256) do update set object_key=excluded.object_key,quality=excluded.quality,record_count=excluded.record_count,validation_status=excluded.validation_status,status=excluded.status returning id""",
          (src,sha,key,Jsonb({'url':IBGE_URL,'http_status':response.status_code}), 'VALIDATED' if validation=='PASS' else 'REJECTED',Jsonb({'checks':checks}),len(data),validation)).fetchone()[0]
        for q in checks:
          c.execute("""insert into data_quality.result(source_id,snapshot_id,check_code,severity,status,expected,observed)
            values(%s,%s,%s,%s,%s,%s,%s) on conflict(snapshot_id,check_code) do update set severity=excluded.severity,status=excluded.status,expected=excluded.expected,observed=excluded.observed,checked_at=now()""",
            (src,snap,q['code'],q['severity'],q['status'],Jsonb(q['expected']),Jsonb(q['observed'])))
        if validation!='PASS':
          c.execute("update source.registry set health='DEGRADED' where id=%s",(src,));raise RuntimeError(f'IBGE snapshot failed {blocking} blocking quality checks')
        count=0
        for m in data:
          code=str(m.get('id',''));name=str(m.get('nome','')).strip();uf=extract_uf(m);sig=str(uf.get('sigla','')).strip();region=str((uf.get('regiao') or {}).get('nome','')).strip()
          if len(code)==7 and code.isdigit() and name and sig:
            c.execute("""insert into core.municipality(ibge_code,name,uf,region,source_snapshot_id,updated_at) values(%s,%s,%s,%s,%s,now())
              on conflict(ibge_code) do update set name=excluded.name,uf=excluded.uf,region=excluded.region,source_snapshot_id=excluded.source_snapshot_id,updated_at=now()""",(code,name,sig,region or None,snap));count+=1
        previous=c.execute("select snapshot_id from source.publication where source_id=%s and municipality_ibge is null and (dataset_code='IBGE_LOCALIDADES' or dataset_code is null) and status='ACTIVE' for update",(src,)).fetchone()
        c.execute("update source.publication set status='INACTIVE',deactivated_at=now() where source_id=%s and municipality_ibge is null and (dataset_code='IBGE_LOCALIDADES' or dataset_code is null) and status='ACTIVE'",(src,))
        c.execute("insert into source.publication(source_id,municipality_ibge,dataset_code,snapshot_id,status) values(%s,null,'IBGE_LOCALIDADES',%s,'ACTIVE')",(src,snap))
        c.execute("update source.snapshot set status='PUBLISHED',published_at=coalesce(published_at,now()) where id=%s",(snap,))
        c.execute("insert into source.publication_event(source_id,dataset_code,previous_snapshot_id,next_snapshot_id,action,actor,reason) values(%s,'IBGE_LOCALIDADES',%s,%s,'ACTIVATE','data-pipelines','automatic activation after PASS quality checks')",(src,previous[0] if previous else None,snap))
    print('IBGE synced',count,sha,'quality',validation,flush=True)


def main():
    while True:
      try:sync_ibge()
      except Exception as exc:print('IBGE sync failed',repr(exc),flush=True)
      for spec in configured_geojson_sources():
        try:print('Geo source sync',sync_geojson_source(spec),flush=True)
        except Exception as exc:print(f"{spec['code']} sync failed",repr(exc),flush=True)
      time.sleep(INTERVAL)

if __name__=='__main__':main()
