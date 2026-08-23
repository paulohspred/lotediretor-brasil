from __future__ import annotations
import hashlib, os, time
import boto3, psycopg
from psycopg.types.json import Jsonb
from builder import build_report, canonical_json
from renderer import render_structured

DB=os.environ['PLATFORM_DATABASE_URL']; BUCKET=os.getenv('S3_BUCKET','lotediretor'); WORKER_VERSION='19.0.0-rc.3'
s3=boto3.client('s3',endpoint_url=os.getenv('S3_ENDPOINT','http://minio:9000'),aws_access_key_id=os.getenv('S3_ACCESS_KEY','lotediretor'),aws_secret_access_key=os.getenv('S3_SECRET_KEY','lotediretor-local-secret'),region_name=os.getenv('S3_REGION','us-east-1'))

def persist_structure(conn, rid, tenant, document):
    conn.execute('delete from report.section where report_run_id=%s and tenant_id=%s',(rid,tenant))
    conn.execute('delete from report.evidence where report_run_id=%s and tenant_id=%s',(rid,tenant))
    for section in document.get('sections') or []:
        conn.execute("""insert into report.section(tenant_id,report_run_id,section_code,ordinal,title,status,summary,payload)
                        values(%s,%s,%s,%s,%s,%s,%s,%s)""",
                     (tenant,rid,section['code'],section['ordinal'],section['title'],section['status'],section.get('summary'),Jsonb(section.get('payload') or {})))
    for ev in document.get('evidence') or []:
        conn.execute("""insert into report.evidence(tenant_id,report_run_id,section_code,evidence_type,source_code,source_snapshot_id,source_document_version_id,source_locator,url,sha256,confidence_status,payload)
                        values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                     (tenant,rid,ev.get('sectionCode'),ev.get('evidenceType'),ev.get('sourceCode'),ev.get('sourceSnapshotId'),ev.get('sourceDocumentVersionId'),ev.get('sourceLocator'),ev.get('url'),ev.get('sha256'),ev.get('confidenceStatus') or 'PENDING',Jsonb(ev.get('payload') or {})))
    raw=canonical_json(document); snapshot_sha=hashlib.sha256(raw).hexdigest()
    conn.execute("""insert into report.snapshot(report_run_id,tenant_id,schema_version,payload,sha256)
                    values(%s,%s,%s,%s,%s)
                    on conflict(report_run_id) do update set schema_version=excluded.schema_version,payload=excluded.payload,sha256=excluded.sha256,created_at=now()""",
                 (rid,tenant,document.get('schemaVersion') or 'report-360-v1',Jsonb(document),snapshot_sha))
    return raw,snapshot_sha

def process_one():
  with psycopg.connect(DB) as conn:
    with conn.transaction():
      row=conn.execute("""select id,tenant_id,kind,subject_type,subject_id,base_date,input_snapshot,template_code,template_version,created_at
                          from report.report_run where status='QUEUED' order by created_at for update skip locked limit 1""").fetchone()
      if not row:return False
      keys=['id','tenant_id','kind','subject_type','subject_id','base_date','input_snapshot','template_code','template_version','created_at']; report_run=dict(zip(keys,row));rid=report_run['id'];tenant=report_run['tenant_id']
      conn.execute("update report.report_run set status='PROCESSING',renderer_version=%s where id=%s",(WORKER_VERSION,rid))
    try:
      document=build_report(conn,str(tenant),report_run)
      pdf=render_structured(document); pdf_sha=hashlib.sha256(pdf).hexdigest(); pdf_key=f'tenant/{tenant}/reports/{rid}/report.pdf'
      json_raw=canonical_json(document); json_sha=hashlib.sha256(json_raw).hexdigest(); json_key=f'tenant/{tenant}/reports/{rid}/manifest.json'
      s3.put_object(Bucket=BUCKET,Key=pdf_key,Body=pdf,ContentType='application/pdf',Metadata={'sha256':pdf_sha,'renderer':WORKER_VERSION})
      s3.put_object(Bucket=BUCKET,Key=json_key,Body=json_raw,ContentType='application/json',Metadata={'sha256':json_sha,'schema':str(document.get('schemaVersion') or '')})
      with conn.transaction():
        persist_structure(conn,rid,tenant,document)
        conn.execute("""update report.report_run set status='COMPLETED',artifact_key=%s,sha256=%s,renderer_version=%s,
                      template_code=%s,template_version=%s,confidence_summary=%s,metadata=metadata||%s,frozen_at=now(),completed_at=now() where id=%s""",
                     (pdf_key,pdf_sha,WORKER_VERSION,document['template']['code'],document['template']['version'],Jsonb(document.get('confidenceSummary') or {}),Jsonb({'jsonArtifactKey':json_key,'jsonSha256':json_sha,'schemaVersion':document.get('schemaVersion')}),rid))
        conn.execute("insert into report.artifact(tenant_id,report_run_id,object_key,content_type,size_bytes,sha256) values(%s,%s,%s,'application/pdf',%s,%s) on conflict(report_run_id,sha256) do nothing",(tenant,rid,pdf_key,len(pdf),pdf_sha))
        conn.execute("insert into report.artifact(tenant_id,report_run_id,object_key,content_type,size_bytes,sha256) values(%s,%s,%s,'application/json',%s,%s) on conflict(report_run_id,sha256) do nothing",(tenant,rid,json_key,len(json_raw),json_sha))
        conn.execute("insert into notification.notification(tenant_id,kind,title,body,status,payload) values(%s,'REPORT_READY','Relatório 360 concluído','PDF e manifesto JSON foram congelados com hashes de integridade.','UNREAD',%s)",(tenant,Jsonb({'reportRunId':str(rid),'pdfSha256':pdf_sha,'jsonSha256':json_sha,'objectKey':pdf_key})))
        conn.execute("insert into event.outbox(tenant_id,topic,aggregate_type,aggregate_id,dedupe_key,payload,status,next_attempt_at) values(%s,'report.completed','report.report_run',%s,%s,%s,'PENDING',now()) on conflict(dedupe_key) where dedupe_key is not null do nothing",(tenant,str(rid),f'report.completed:{rid}',Jsonb({'reportRunId':str(rid),'pdfSha256':pdf_sha,'jsonSha256':json_sha,'objectKey':pdf_key})))
    except Exception as exc:
      with conn.transaction(): conn.execute("update report.report_run set status='FAILED',metadata=metadata||%s where id=%s",(Jsonb({'workerError':str(exc)[:1000],'workerVersion':WORKER_VERSION}),rid))
      print('report failed',rid,exc,flush=True)
  return True

def main():
  while True:
    try:
      if not process_one():time.sleep(3)
    except Exception as exc:print('report loop error',exc,flush=True);time.sleep(5)

if __name__=='__main__': main()
