from __future__ import annotations
import argparse, hashlib, json, os, re
from datetime import datetime, timezone
from html.parser import HTMLParser
import requests, psycopg
from psycopg.types.json import Jsonb
from connectors import s3_client

DB=os.environ['PLATFORM_DATABASE_URL'];S3_BUCKET=os.getenv('S3_BUCKET','lotediretor')

class VisibleText(HTMLParser):
    def __init__(self): super().__init__();self.out=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','nav','footer'}: self.skip+=1
        if tag in {'p','div','br','li','h1','h2','h3','h4','tr'} and not self.skip:self.out.append('\n')
    def handle_endtag(self,tag):
        if tag in {'script','style','nav','footer'} and self.skip:self.skip-=1
        if tag in {'p','div','li','h1','h2','h3','h4','tr'} and not self.skip:self.out.append('\n')
    def handle_data(self,data):
        if not self.skip:self.out.append(data)

def html_to_text(raw:str)->str:
    p=VisibleText();p.feed(raw);text=''.join(p.out).replace('\xa0',' ')
    text=re.sub(r'[ \t]+',' ',text);text=re.sub(r'\n{3,}','\n\n',text)
    return text.strip()

def articles(text:str)->list[dict]:
    # Conservative structural splitter: captures article boundaries only; paragraphs/incisos remain in body until later parser stages.
    matches=list(re.finditer(r'(?im)^\s*(Art\.?\s*\d+[ºo]?\.?[^\n]*)',text))
    if not matches:return [{'path':'DOCUMENT','label':'DOCUMENT','body':text,'ordinal':1}]
    out=[]
    for i,m in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(text);label=m.group(1).strip();body=text[m.start():end].strip()
        out.append({'path':f'ARTICLE/{i+1:05d}','label':label,'body':body,'ordinal':i+1})
    return out

def ingest(source_code:str,municipality:str,url:str,title:str,kind:str,version_label:str,effective_date:str|None,status:str='REVIEWED')->dict:
    if status not in {'DRAFT','REVIEWED'}:raise RuntimeError('automatic legal ingestion may only create DRAFT/REVIEWED versions')
    r=requests.get(url,headers={'user-agent':'LoteDiretor/19-rc1','accept':'text/html,application/xhtml+xml'},timeout=120);r.raise_for_status();raw=r.content;sha=hashlib.sha256(raw).hexdigest();text=html_to_text(r.text);parts=articles(text)
    if len(text)<500:raise RuntimeError('legal source text unexpectedly short')
    key=f"municipality/{municipality}/legal/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{sha}.html";txt_key=key[:-5]+'.txt'
    s3=s3_client();s3.put_object(Bucket=S3_BUCKET,Key=key,Body=raw,ContentType=r.headers.get('content-type','text/html'),Metadata={'sha256':sha,'source':source_code});s3.put_object(Bucket=S3_BUCKET,Key=txt_key,Body=text.encode(),ContentType='text/plain; charset=utf-8',Metadata={'sha256':hashlib.sha256(text.encode()).hexdigest(),'source':source_code})
    with psycopg.connect(DB) as c, c.transaction():
        source_row=c.execute("select id,authority from source.registry where code=%s",(source_code,)).fetchone()
        if not source_row:raise RuntimeError(f'unknown source registry code: {source_code}')
        source_id,source_authority=source_row
        snap=c.execute("""insert into source.snapshot(source_id,source_date,parser_version,sha256,object_key,metadata,status,quality,record_count,validation_status,schema_version)
          values(%s,now(),'legal-html-v19-rc2',%s,%s,%s,'VALIDATED',%s,%s,'PASS','legal-html-v1')
          on conflict(source_id,sha256) do update set object_key=excluded.object_key,metadata=excluded.metadata,quality=excluded.quality,record_count=excluded.record_count,validation_status='PASS' returning id""",
          (source_id,sha,key,Jsonb({'url':url,'http_status':r.status_code,'text_object_key':txt_key}),Jsonb({'text_chars':len(text),'article_count':len(parts)}),len(parts))).fetchone()[0]
        existing_doc=c.execute("""select id from legal.document where municipality_ibge=%s and tenant_id is null and kind=%s and title=%s and authority=%s order by created_at limit 1""",(municipality,kind,title,source_authority)).fetchone()
        doc=existing_doc[0] if existing_doc else c.execute("""insert into legal.document(municipality_ibge,tenant_id,kind,title,authority,visibility) values(%s,null,%s,%s,%s,'PUBLIC') returning id""",(municipality,kind,title,source_authority)).fetchone()[0]
        existing_version=c.execute("select id from legal.document_version where document_id=%s and sha256=%s order by recorded_at desc limit 1",(doc,sha)).fetchone()
        dv=existing_version[0] if existing_version else c.execute("""insert into legal.document_version(document_id,source_snapshot_id,version_label,publication_date,effective_date,valid_from,text_object_key,sha256,status) values(%s,%s,%s,null,%s,%s,%s,%s,%s) returning id""",
          (doc,snap,version_label,effective_date,effective_date,txt_key,sha,status)).fetchone()[0]
        if not existing_version and effective_date:
          # Same canonical act, newer explicit effective date: close the prior legal-time interval and record system supersession.
          c.execute("""update legal.document_version set valid_to=%s::timestamptz,superseded_at=now() where document_id=%s and id<>%s and valid_to is null and valid_from is not null and valid_from < %s::timestamptz""",(effective_date,doc,dv,effective_date))
        if not existing_version:
          for part in parts:
            c.execute("""insert into legal.article(document_version_id,hierarchy_path,article_type,label,body_text,ordinal,source_locator) values(%s,%s,'ARTICLE',%s,%s,%s,%s)""",(dv,part['path'],part['label'],part['body'],part['ordinal'],part['label']))
        # Public legal knowledge is indexed as a derived corpus. The version id is used as document_id
        # so multiple historical versions can coexist without chunk-key collisions.
        c.execute("delete from ingest.document_text where domain='municipality' and document_id=%s",(dv,))
        for idx,part in enumerate(parts):
          c.execute("""insert into ingest.document_text(tenant_id,domain,document_id,chunk_index,text_content,metadata,document_title,source_locator,section_id,municipality_ibge,visibility,knowledge_status,retrieval_allowed,valid_from,valid_to,recorded_at,superseded_at,document_version_id,source_snapshot_id,acl)
            values(null,'municipality',%s,%s,%s,%s,%s,%s,%s,%s,'PUBLIC',%s,%s,%s,null,now(),null,%s,%s,'{"public":true}'::jsonb)""",
            (dv,idx,part['body'],Jsonb({'source_code':source_code,'source_url':url,'document_kind':kind,'version_label':version_label}),title,part['label'],part['path'],municipality,status,status in {'REVIEWED','PUBLISHED','ACTIVE','CONFIRMED'},effective_date,dv,snap))
        coverage_code='PLANO_DIRETOR' if kind.upper() in {'PLANO_DIRETOR','PDE'} else kind.upper()
        c.execute("""update source.coverage set availability_status='AVAILABLE',ingestion_status='VALIDATED',parser_version='legal-html-v19-rc2',last_checked_at=now(),last_source_update=now(),evidence_hash=%s,metadata=metadata||%s where source_id=%s and municipality_ibge=%s and dataset_code=%s""",(sha,Jsonb({'document_version_id':str(dv),'articles':len(parts),'automatic_rule_status':'CANDIDATE_ONLY'}),source_id,municipality,coverage_code))
    return {'status':status,'snapshotId':str(snap),'documentId':str(doc),'documentVersionId':str(dv),'sha256':sha,'articles':len(parts),'note':'No legal.rule is confirmed automatically.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--source-code',required=True);p.add_argument('--municipality',required=True);p.add_argument('--url',required=True);p.add_argument('--title',required=True);p.add_argument('--kind',default='PLANO_DIRETOR');p.add_argument('--version-label',required=True);p.add_argument('--effective-date');a=p.parse_args()
    print(json.dumps(ingest(a.source_code,a.municipality,a.url,a.title,a.kind,a.version_label,a.effective_date),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
