from __future__ import annotations
import os,time,requests,psycopg

DB=os.environ['PLATFORM_DATABASE_URL']
OPENSEARCH=os.getenv('OPENSEARCH_URL','').rstrip('/')
INDEX=os.getenv('OPENSEARCH_EVIDENCE_INDEX','lotediretor-evidence-v3')
INTERVAL=float(os.getenv('AI_INDEX_INTERVAL_SECONDS','2'))
EMBED_ENDPOINT=os.getenv('AI_EMBEDDINGS_ENDPOINT','').strip()
EMBED_MODEL=os.getenv('AI_EMBEDDINGS_MODEL','').strip()
EMBED_KEY=os.getenv('AI_EMBEDDINGS_API_KEY',os.getenv('AI_API_KEY','')).strip()
EMBED_DIM=max(1,int(os.getenv('AI_EMBEDDINGS_DIMENSION','1536')))
OS_USER=os.getenv('OPENSEARCH_USERNAME','').strip();OS_PASSWORD=os.getenv('OPENSEARCH_PASSWORD','').strip()


def _auth(): return (OS_USER,OS_PASSWORD) if (OS_USER or OS_PASSWORD) else None


def index_properties():
    return {
      'tenant_id':{'type':'keyword'},'domain':{'type':'keyword'},'document_id':{'type':'keyword'},'document_version_id':{'type':'keyword'},
      'source_snapshot_id':{'type':'keyword'},'chunk_index':{'type':'integer'},'scope_id':{'type':'keyword'},'municipality_ibge':{'type':'keyword'},
      'visibility':{'type':'keyword'},'knowledge_status':{'type':'keyword'},'retrieval_allowed':{'type':'boolean'},
      'title':{'type':'text','analyzer':'portuguese','fields':{'keyword':{'type':'keyword','ignore_above':512}}},
      'locator':{'type':'keyword','ignore_above':1024},'page_number':{'type':'integer'},'section_id':{'type':'keyword','ignore_above':1024},
      'text':{'type':'text','analyzer':'portuguese'},'valid_from':{'type':'date'},'valid_to':{'type':'date'},'recorded_at':{'type':'date'},'superseded_at':{'type':'date'},
      'metadata':{'type':'object','enabled':False},'acl':{'type':'object','enabled':False},'embedding_model':{'type':'keyword'},
      'embedding':{'type':'knn_vector','dimension':EMBED_DIM,'method':{'name':'hnsw','space_type':'cosinesimil','engine':'lucene','parameters':{'ef_construction':128,'m':16}}}
    }


def wait_for_opensearch(timeout_seconds:float=180.0):
    if not OPENSEARCH:return False
    deadline=time.monotonic()+timeout_seconds
    last_error='not_attempted'
    while time.monotonic()<deadline:
        try:
            r=requests.get(f'{OPENSEARCH}/_cluster/health',params={'wait_for_status':'yellow','timeout':'5s'},auth=_auth(),timeout=10)
            if r.ok:
                payload=r.json() if r.content else {}
                if payload.get('status') in {'yellow','green'}:
                    return True
            last_error=f'http_{r.status_code}:{r.text[:300]}'
        except requests.RequestException as exc:
            last_error=repr(exc)
        time.sleep(2)
    raise RuntimeError(f'opensearch_not_ready_after_{timeout_seconds}s:{last_error}')


def ensure_index():
    if not OPENSEARCH:return False
    mapping={'settings':{'index':{'knn':True}},'mappings':{'dynamic':'strict','properties':index_properties()}}
    head=requests.head(f'{OPENSEARCH}/{INDEX}',auth=_auth(),timeout=10)
    if head.status_code==404:
        r=requests.put(f'{OPENSEARCH}/{INDEX}',json=mapping,auth=_auth(),timeout=15);r.raise_for_status();return True
    if head.status_code>=400:head.raise_for_status()
    # Additive mapping upgrade for an existing compatible index. Dimension changes require a new index name.
    r=requests.put(f'{OPENSEARCH}/{INDEX}/_mapping',json={'properties':index_properties()},auth=_auth(),timeout=15)
    if r.status_code>=400:
        raise RuntimeError(f'opensearch_mapping_upgrade_rejected:{r.text[:1200]}')
    return True


def embed(text:str):
    if not (EMBED_ENDPOINT and EMBED_MODEL and EMBED_KEY):return None
    r=requests.post(EMBED_ENDPOINT,headers={'authorization':f'Bearer {EMBED_KEY}','content-type':'application/json'},json={'model':EMBED_MODEL,'input':text[:24000],'encoding_format':'float'},timeout=float(os.getenv('AI_EMBEDDINGS_TIMEOUT_SECONDS','20')))
    r.raise_for_status();raw=r.json();vec=((raw.get('data') or [{}])[0].get('embedding') if isinstance(raw,dict) else None) or (raw.get('embedding') if isinstance(raw,dict) else None)
    if not isinstance(vec,list) or len(vec)!=EMBED_DIM:raise RuntimeError(f'embedding_dimension_invalid:{len(vec) if isinstance(vec,list) else "none"}:expected:{EMBED_DIM}')
    return [float(x) for x in vec]


def process_one():
    if not OPENSEARCH:return False
    with psycopg.connect(DB) as c:
      with c.transaction():
        row=c.execute("""select id,tenant_id,domain,document_id,chunk_index,text_content,metadata,document_title,source_locator,page_number,section_id,
          scope_id,municipality_ibge,visibility,knowledge_status,retrieval_allowed,valid_from,valid_to,recorded_at,superseded_at,document_version_id,source_snapshot_id,acl
          from ingest.document_text where indexed_at is null order by created_at for update skip locked limit 1""").fetchone()
        if not row:return False
        (rid,tenant,domain,doc,idx,text,metadata,title,locator,page_number,section_id,scope_id,municipality_ibge,visibility,knowledge_status,retrieval_allowed,
         valid_from,valid_to,recorded_at,superseded_at,document_version_id,source_snapshot_id,acl)=row
      try:
        payload={
          'tenant_id':str(tenant) if tenant else None,'domain':domain,'document_id':str(doc),'chunk_index':idx,'text':text,
          'title':title or f'{domain}:{doc}','locator':locator or f'document:{doc}#chunk-{idx}','visibility':visibility or 'PRIVATE',
          'knowledge_status':knowledge_status or 'DRAFT','retrieval_allowed':bool(retrieval_allowed),'metadata':metadata or {},'acl':acl or {}
        }
        optional={'page_number':page_number,'section_id':section_id,'scope_id':scope_id,'municipality_ibge':municipality_ibge,
                  'valid_from':valid_from,'valid_to':valid_to,'recorded_at':recorded_at,'superseded_at':superseded_at,'document_version_id':document_version_id,'source_snapshot_id':source_snapshot_id}
        for k,v in optional.items():
            if v is not None:payload[k]=str(v) if k in {'document_version_id','source_snapshot_id'} else v.isoformat() if hasattr(v,'isoformat') else v
        # Embeddings are derived only for content allowed to participate in retrieval. Drafts remain indexed lexically-disabled
        # by retrieval_allowed=false so a later homologation can reindex safely without exposing content prematurely.
        vector=embed(text) if retrieval_allowed else None
        if vector is not None:payload.update(embedding=vector,embedding_model=EMBED_MODEL)
        r=requests.put(f'{OPENSEARCH}/{INDEX}/_doc/{rid}',json=payload,auth=_auth(),timeout=20);r.raise_for_status()
        with c.transaction():c.execute('update ingest.document_text set indexed_at=now(),index_error=null where id=%s',(rid,))
      except Exception as exc:
        with c.transaction():c.execute('update ingest.document_text set index_error=%s where id=%s',(str(exc)[:1000],rid))
        raise
    return True


def main():
    if not OPENSEARCH:
      print('ai-ingest disabled: OPENSEARCH_URL not configured',flush=True)
      while True:time.sleep(60)
    wait_for_opensearch(float(os.getenv('OPENSEARCH_STARTUP_TIMEOUT_SECONDS','180')))
    ensure_index()
    print(f'ai-ingest index={INDEX} embeddings={bool(EMBED_ENDPOINT and EMBED_MODEL and EMBED_KEY)} dimension={EMBED_DIM}',flush=True)
    while True:
      try:
        if not process_one():time.sleep(INTERVAL)
      except Exception as exc:print('ai-ingest error',repr(exc),flush=True);time.sleep(5)

if __name__=='__main__':main()
