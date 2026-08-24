const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ld-ai-retrieval-v20-'));
function compile(rel,name){
  const src=fs.readFileSync(path.join(root,rel),'utf8');
  const out=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
  const dst=path.join(tmp,name);fs.writeFileSync(dst,out);return dst;
}
compile('services/ai-gateway/src/embeddings.ts','embeddings.js');
compile('services/ai-gateway/src/retrieval.ts','retrieval.js');

process.env.OPENSEARCH_URL='http://opensearch.test:9200';
process.env.OPENSEARCH_EVIDENCE_INDEX='evidence-test';
process.env.AI_RETRIEVAL_CACHE_TTL_MS='60000';
process.env.AI_RETRIEVAL_CACHE_MAX_ENTRIES='10';
delete process.env.AI_EMBEDDINGS_ENDPOINT;
delete process.env.AI_EMBEDDINGS_MODEL;
delete process.env.AI_EMBEDDINGS_API_KEY;
delete process.env.AI_API_KEY;

const calls=[];
global.fetch=async(url,options={})=>{
  const body=JSON.parse(options.body||'{}');
  calls.push({url:String(url),body});
  const expansion=Array.isArray(body.sort);
  if(expansion){
    return{ok:true,status:200,json:async()=>({hits:{hits:[
      {_id:'ctx-9',_score:1,_source:{tenant_id:'tenant-a',domain:'municipality',document_id:'doc-1',document_version_id:'dv-1',source_snapshot_id:'snap-1',chunk_index:9,section_id:'ARTICLE/00010',text:'Contexto anterior do mesmo artigo.',title:'Lei teste',locator:'Art. 10 contexto'}},
      {_id:'seed-10',_score:1,_source:{tenant_id:'tenant-a',domain:'municipality',document_id:'doc-1',document_version_id:'dv-1',source_snapshot_id:'snap-1',chunk_index:10,section_id:'ARTICLE/00010',text:'Texto principal.',title:'Lei teste',locator:'Art. 10'}}
    ]}})};
  }
  return{ok:true,status:200,json:async()=>({hits:{hits:[
    {_id:'seed-10',_score:2,_source:{tenant_id:'tenant-a',domain:'municipality',document_id:'doc-1',document_version_id:'dv-1',source_snapshot_id:'snap-1',chunk_index:10,section_id:'ARTICLE/00010',visibility:'PRIVATE',knowledge_status:'REVIEWED',recorded_at:'2026-01-01T00:00:00Z',text:'A Lei 123 estabelece o conteúdo do artigo dez.',title:'Lei 123',locator:'Art. 10'}}
  ]}})};
};

const retrieval=require(path.join(tmp,'retrieval.js'));
(async()=>{
  const pinned={
    sourceSnapshotIds:['snap-1'],
    documentVersionIds:['dv-1'],
    knowledgeAt:'2026-08-23T12:00:00Z',
    baseDate:'2026-08-23',
    includePublic:false,
    expandContext:true,
    ruleSetHash:'rules-sha256'
  };
  const keyA=retrieval.pinnedRetrievalCacheKey('tenant-a','Lei 123',pinned);
  const keyB=retrieval.pinnedRetrievalCacheKey('tenant-b','Lei 123',pinned);
  assert.equal(typeof keyA,'string');assert.equal(keyA.length,64);assert.notEqual(keyA,keyB);
  assert.equal(retrieval.pinnedRetrievalCacheKey('tenant-a','Lei 123',{knowledgeAt:pinned.knowledgeAt}),null);
  assert.equal(retrieval.pinnedRetrievalCacheKey('tenant-a','Lei 123',{sourceSnapshotIds:['snap-1']}),null);

  const first=await retrieval.retrieveEvidence('tenant-a','Lei 123',pinned);
  assert.equal(first.items.length,1);
  assert.equal(first.contextItems.length,1);
  assert.equal(first.contextItems[0].id,'ctx-9');
  assert.equal(first.contextItems[0].contextOf,'seed-10');
  assert.equal(first.cache.eligible,true);assert.equal(first.cache.hit,false);
  assert.deepEqual(first.sourceSnapshotIds,['snap-1']);
  assert.equal(first.hierarchyExpansion,'same_section_or_adjacent_chunks');
  assert.equal(calls.length,2);

  const firstBody=JSON.stringify(calls[0].body);
  const expansionBody=JSON.stringify(calls[1].body);
  for(const required of ['tenant-a','source_snapshot_id','snap-1','document_version_id','dv-1','recorded_at','superseded_at']){
    assert(firstBody.includes(required),`primary missing ${required}`);
    assert(expansionBody.includes(required),`expansion missing ${required}`);
  }
  assert(expansionBody.includes('chunk_index'));
  assert(expansionBody.includes('ARTICLE/00010'));

  const cached=await retrieval.retrieveEvidence('tenant-a','Lei 123',pinned);
  assert.equal(cached.cache.hit,true);
  assert.equal(calls.length,2,'pinned repeated retrieval should be served from cache');

  const tenantB=await retrieval.retrieveEvidence('tenant-b','Lei 123',pinned);
  assert.equal(tenantB.cache.hit,false);
  assert.equal(calls.length,4,'tenant must be part of cache identity');
  assert(JSON.stringify(calls[2].body).includes('tenant-b'));

  const unpinned=await retrieval.retrieveEvidence('tenant-a','Lei 123',{knowledgeAt:pinned.knowledgeAt,includePublic:false,expandContext:false});
  assert.equal(unpinned.cache.eligible,false);
  assert.equal(unpinned.cache.hit,false);
  assert.equal(calls.length,5,'un-pinned retrieval must never reuse pinned cache');

  retrieval.clearPinnedRetrievalCache();
  console.log('v20 AI pinned retrieval cache/context expansion OK');
})().catch(error=>{console.error(error);process.exit(1)});
