from __future__ import annotations
import hashlib, io, os, time, zipfile
from html import escape
import boto3, psycopg
from psycopg.types.json import Jsonb

DB=os.environ['PLATFORM_DATABASE_URL']; BUCKET=os.getenv('S3_BUCKET','lotediretor'); VERSION='19.0.0-rc.3'
s3=boto3.client('s3',endpoint_url=os.getenv('S3_ENDPOINT','http://minio:9000'),aws_access_key_id=os.getenv('S3_ACCESS_KEY','lotediretor'),aws_secret_access_key=os.getenv('S3_SECRET_KEY','lotediretor-local-secret'),region_name=os.getenv('S3_REGION','us-east-1'))

from exporter import kml_document,package_export

def process_one():
    with psycopg.connect(DB) as conn:
      with conn.transaction():
        row=conn.execute("select id,tenant_id,asset_id,format from rural.export_job where status='QUEUED' order by created_at for update skip locked limit 1").fetchone()
        if not row:return False
        jid,tenant,asset_id,fmt=row;conn.execute("update rural.export_job set status='PROCESSING' where id=%s",(jid,))
      try:
        a=conn.execute("select id,name,municipality_ibge,st_asgeojson(geom)::jsonb geometry from rural.asset where id=%s and tenant_id=%s",(asset_id,tenant)).fetchone()
        if not a:raise ValueError('asset_not_found')
        asset=dict(zip(['id','name','municipality_ibge','geometry'],a))
        cur=conn.execute("select registry_type,official_identifier,st_asgeojson(geom)::jsonb geometry from rural.registry_record where asset_id=%s and geom is not null order by registry_type",(asset_id,));records=[dict(zip(['registry_type','official_identifier','geometry'],r)) for r in cur.fetchall()]
        kml=kml_document(asset,records)
        payload,ext,ctype=package_export(kml,fmt)
        sha=hashlib.sha256(payload).hexdigest();key=f'tenant/{tenant}/rural/{asset_id}/exports/{jid}.{ext}'
        s3.put_object(Bucket=BUCKET,Key=key,Body=payload,ContentType=ctype,Metadata={'sha256':sha,'worker':VERSION})
        with conn.transaction():
            conn.execute("update rural.export_job set status='COMPLETED',object_key=%s,sha256=%s,size_bytes=%s,metadata=metadata||%s,completed_at=now() where id=%s",(key,sha,len(payload),Jsonb({'workerVersion':VERSION,'registryGeometries':len(records)}),jid))
            conn.execute("insert into event.outbox(tenant_id,topic,aggregate_type,aggregate_id,dedupe_key,payload,status,next_attempt_at) values(%s,'rural.export.completed','rural.export_job',%s,%s,%s,'PENDING',now()) on conflict(dedupe_key) where dedupe_key is not null do nothing",(tenant,str(jid),f'rural.export.completed:{jid}',Jsonb({'exportJobId':str(jid),'assetId':str(asset_id),'format':fmt,'sha256':sha})))
      except Exception as exc:
        with conn.transaction():conn.execute("update rural.export_job set status='FAILED',metadata=metadata||%s,completed_at=now() where id=%s",(Jsonb({'error':str(exc)[:1000],'workerVersion':VERSION}),jid))
      return True

def main():
    while True:
        try:
            if not process_one():time.sleep(3)
        except Exception as exc:print('rural-export loop error',exc,flush=True);time.sleep(5)
if __name__=='__main__':main()
