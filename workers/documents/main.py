from __future__ import annotations
import hashlib, io, os, subprocess, tempfile, time
import boto3, psycopg
from psycopg.types.json import Jsonb
from pypdf import PdfReader
from rules import condo_candidates, legal_units, legal_candidates
from chunking import semantic_chunks

DB=os.environ['PLATFORM_DATABASE_URL']; BUCKET=os.getenv('S3_BUCKET','lotediretor')
s3=boto3.client('s3',endpoint_url=os.getenv('S3_ENDPOINT','http://minio:9000'),aws_access_key_id=os.getenv('S3_ACCESS_KEY','lotediretor'),aws_secret_access_key=os.getenv('S3_SECRET_KEY','lotediretor-local-secret'),region_name=os.getenv('S3_REGION','us-east-1'))

def extract_pdf(data:bytes)->tuple[str,bool]:
    def read(buf:bytes)->str:
        r=PdfReader(io.BytesIO(buf)); return '\n'.join(f'<<<PAGE:{i+1}>>>\n'+(p.extract_text() or '') for i,p in enumerate(r.pages))
    text=read(data)
    if len(text.strip())>=120: return text,False
    with tempfile.TemporaryDirectory() as td:
        src=f'{td}/in.pdf'; out=f'{td}/ocr.pdf'; open(src,'wb').write(data)
        subprocess.run(['ocrmypdf','--language','por','--skip-text','--deskew',src,out],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=300)
        return read(open(out,'rb').read()),True

def process_one():
    with psycopg.connect(DB) as conn:
      with conn.transaction():
        row=conn.execute("select id,tenant_id,domain,document_id,object_key,sha256,metadata from ingest.document_job where status='QUEUED' order by created_at for update skip locked limit 1").fetchone()
        if not row:return False
        jid,tenant,domain,docid,key,expected,meta=row
        conn.execute("update ingest.document_job set status='PROCESSING',attempts=attempts+1,started_at=now(),error=null where id=%s",(jid,))
      try:
        data=s3.get_object(Bucket=BUCKET,Key=key)['Body'].read()
        actual=hashlib.sha256(data).hexdigest()
        if actual!=expected: raise ValueError('sha256_mismatch')
        filename=(meta or {}).get('filename','').lower(); ctype=(meta or {}).get('contentType','')
        if filename.endswith('.pdf') or ctype=='application/pdf': text,ocr=extract_pdf(data)
        else: text=data.decode('utf-8','replace'); ocr=False
        parts=semantic_chunks(text)
        if not parts: raise ValueError('no_text_extracted')
        with conn.transaction():
          conn.execute('delete from ingest.document_text where domain=%s and document_id=%s',(domain,docid))
          for part in parts:
            md_chunk={'ocr':ocr,'sha256':actual,'page_number':part.get('page_number'),'locator':part.get('locator')}
            conn.execute("insert into ingest.document_text(tenant_id,domain,document_id,chunk_index,text_content,metadata,page_number,source_locator) values(%s,%s,%s,%s,%s,%s,%s,%s)",(tenant,domain,docid,part['index'],part['text'],Jsonb(md_chunk),part.get('page_number'),part.get('locator')))
          if domain=='condo':
            conn.execute('delete from condo.document_chunk where document_id=%s',(docid,))
            condo_id=conn.execute("select condominium_id from condo.document where id=%s",(docid,)).fetchone()[0]
            for part in parts:
              locator=f'document:{docid}#{part["locator"]}'
              chunk_id=conn.execute("insert into condo.document_chunk(tenant_id,document_id,chunk_index,text_content,metadata) values(%s,%s,%s,%s,%s) returning id",(tenant,docid,part['index'],part['text'],Jsonb({'ocr':ocr,'sha256':actual,'page_number':part.get('page_number'),'locator':locator}))).fetchone()[0]
              conn.execute("insert into condo.evidence_link(tenant_id,condominium_id,document_id,chunk_id,locator) values(%s,%s,%s,%s,%s)",(tenant,condo_id,docid,chunk_id,locator))
              conn.execute("update ingest.document_text set document_title=(select title from condo.document where id=%s),scope_id=%s,visibility='PRIVATE',knowledge_status='PROCESSED',retrieval_allowed=true,source_locator=%s where domain='condo' and document_id=%s and chunk_index=%s",(docid,str(condo_id),locator,docid,part['index']))
            # Reprocessing replaces only deterministic candidates from this document;
            # reviewed/manual rules remain untouched.
            conn.execute("delete from condo.rule where document_id=%s and status='CANDIDATE' and extraction_method='deterministic_condo_v18'",(docid,))
            candidate_count=0
            for cand in condo_candidates(text):
              rid=conn.execute("insert into condo.rule(tenant_id,condominium_id,document_id,rule_type,title,rule_text,status,source_locator,extraction_method,confidence) values(%s,%s,%s,%s,%s,%s,'CANDIDATE',%s,'deterministic_condo_v18',%s) returning id",(tenant,condo_id,docid,cand['rule_type'],cand['title'],cand['rule_text'],cand['source_locator'],cand['confidence'])).fetchone()[0]
              conn.execute("insert into condo.evidence_link(tenant_id,condominium_id,rule_id,document_id,locator) values(%s,%s,%s,%s,%s)",(tenant,condo_id,rid,docid,cand['source_locator']))
              candidate_count+=1
            conn.execute("update condo.document set processing_status='PROCESSED',processed_at=now(),processing_error=null where id=%s",(docid,))
          elif domain=='municipality':
            md=conn.execute("select d.title,d.kind,t.municipality_ibge from municipality.document d join municipality.tenant t on t.id=d.municipality_tenant_id where d.id=%s",(docid,)).fetchone()
            candidate_count=0
            if md:
              title,kind,municipality_ibge=md
              linked=conn.execute("select legal_document_id from municipality.document where id=%s",(docid,)).fetchone()
              legal_doc=linked[0] if linked and linked[0] else conn.execute("insert into legal.document(municipality_ibge,tenant_id,kind,title,authority,visibility) values(%s,%s,%s,%s,'PREFEITURA_UPLOAD','INSTITUTIONAL') returning id",(municipality_ibge,tenant,kind or 'LEGAL',title)).fetchone()[0]
              conn.execute("update municipality.document set legal_document_id=%s where id=%s",(legal_doc,docid))
              prior=conn.execute("select id from legal.document_version where document_id=%s and sha256=%s order by recorded_at desc limit 1",(legal_doc,actual)).fetchone()
              legal_ver=prior[0] if prior else conn.execute("insert into legal.document_version(document_id,version_label,recorded_at,text_object_key,sha256,status) values(%s,%s,now(),%s,%s,'EXTRACTED') returning id",(legal_doc,'upload-'+str(docid),key,actual)).fetchone()[0]
              conn.execute("update municipality.document set legal_document_version_id=%s where id=%s",(legal_ver,docid))
              conn.execute("delete from legal.article where document_version_id=%s",(legal_ver,))
              conn.execute("delete from municipality.rule_review where legal_rule_id in (select id from legal.rule where source_document_version_id=%s and status='CANDIDATE')",(legal_ver,))
              conn.execute("delete from legal.rule where source_document_version_id=%s and status='CANDIDATE'",(legal_ver,))
              units=legal_units(text)
              article_ids={}
              for u in units:
                aid=conn.execute("insert into legal.article(document_version_id,hierarchy_path,article_type,label,heading,body_text,ordinal,source_locator) values(%s,%s,%s,%s,%s,%s,%s,%s) returning id",(legal_ver,u['hierarchy_path'],u['article_type'],u.get('label'),u.get('heading'),u['body_text'],u['ordinal'],u['source_locator'])).fetchone()[0]
                article_ids[u['hierarchy_path']]=aid
              workspace=conn.execute("select municipality_tenant_id from municipality.document where id=%s",(docid,)).fetchone()[0]
              conn.execute("update ingest.document_text set document_title=%s,scope_id=%s,municipality_ibge=%s,visibility='INSTITUTIONAL',knowledge_status=(select status from legal.document_version where id=%s),retrieval_allowed=((select status from legal.document_version where id=%s) in ('REVIEWED','PUBLISHED','ACTIVE','CONFIRMED')),document_version_id=%s,valid_from=(select valid_from from legal.document_version where id=%s),valid_to=(select valid_to from legal.document_version where id=%s),recorded_at=(select recorded_at from legal.document_version where id=%s),superseded_at=(select superseded_at from legal.document_version where id=%s),source_snapshot_id=(select source_snapshot_id from legal.document_version where id=%s) where domain='municipality' and document_id=%s",(title,str(workspace),municipality_ibge,legal_ver,legal_ver,legal_ver,legal_ver,legal_ver,legal_ver,legal_ver,legal_ver,docid))
              searchable=[u for u in units if u['article_type']=='ARTICLE'] or units
              for u in searchable:
                for cand in legal_candidates(u['body_text'],u['source_locator']):
                  extraction={'extractor':cand.get('extractor','deterministic_legal_v19_beta'),'excerpt':cand['excerpt'],'offset':cand['offset'],'article_path':u['hierarchy_path']}
                  rule=conn.execute("insert into legal.rule(municipality_ibge,parameter,value_numeric,unit,condition,extraction_metadata,source_document_version_id,source_article_id,source_locator,status) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,'CANDIDATE') returning id",(municipality_ibge,cand['parameter'],cand['value'],cand['unit'],Jsonb(cand.get('condition') or {}),Jsonb(extraction),legal_ver,article_ids.get(u['hierarchy_path']),cand['source_locator'] or u['source_locator'])).fetchone()[0]
                  conn.execute("insert into municipality.rule_review(municipality_tenant_id,legal_rule_id,status) values(%s,%s,'PENDING')",(workspace,rule))
                  candidate_count+=1
            conn.execute("update municipality.document set processing_status='PROCESSED',processed_at=now(),processing_error=null where id=%s",(docid,))
          else: candidate_count=0
          metadata={'ocr':ocr,'chunks':len(parts)}
          if domain in ('municipality','condo'): metadata['candidate_rules']=candidate_count
          conn.execute("update ingest.document_job set status='COMPLETED',completed_at=now(),metadata=metadata||%s::jsonb where id=%s",(Jsonb(metadata),jid))
          conn.execute("insert into event.outbox(tenant_id,topic,aggregate_type,aggregate_id,dedupe_key,payload,status,next_attempt_at) values(%s,'document.processed','ingest.document_job',%s,%s,%s,'PENDING',now()) on conflict(dedupe_key) where dedupe_key is not null do nothing",(tenant,str(jid),f'document.processed:{jid}',Jsonb({'jobId':str(jid),'domain':domain,'documentId':str(docid),'metadata':metadata})))
      except Exception as exc:
        with conn.transaction():
          conn.execute("update ingest.document_job set status=case when attempts>=3 then 'FAILED' else 'QUEUED' end,error=%s where id=%s",(str(exc)[:1500],jid))
          if domain=='condo': conn.execute("update condo.document set processing_status='ERROR',processing_error=%s where id=%s",(str(exc)[:1500],docid))
          elif domain=='municipality': conn.execute("update municipality.document set processing_status='ERROR',processing_error=%s where id=%s",(str(exc)[:1500],docid))
        print('document job failed',jid,exc,flush=True)
    return True

def main():
    while True:
        try:
            if not process_one(): time.sleep(3)
        except Exception as exc:
            print('worker loop error',exc,flush=True); time.sleep(5)

if __name__=='__main__':
    main()
