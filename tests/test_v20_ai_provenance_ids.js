const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ld-ai-provenance-v20-'));
function compile(rel,name){
  const src=fs.readFileSync(path.join(root,rel),'utf8');
  const out=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
  const dst=path.join(tmp,name);fs.writeFileSync(dst,out);return dst;
}
compile('services/ai-gateway/src/embeddings.ts','embeddings.js');
compile('services/ai-gateway/src/retrieval.ts','retrieval.js');

process.env.OPENSEARCH_URL='http://opensearch.test:9200';
process.env.OPENSEARCH_EVIDENCE_INDEX='evidence-test';
delete process.env.AI_EMBEDDINGS_ENDPOINT;
delete process.env.AI_EMBEDDINGS_MODEL;
delete process.env.AI_EMBEDDINGS_API_KEY;
delete process.env.AI_API_KEY;

global.fetch=async()=>({
  ok:true,
  status:200,
  json:async()=>({hits:{hits:[{
    _id:'no-snapshot',
    _score:5,
    _source:{
      tenant_id:'tenant-a',domain:'runtime-ai',document_id:'doc-1',chunk_index:0,
      source_snapshot_id:null,visibility:'PRIVATE',knowledge_status:'CONFIRMED',
      recorded_at:'2026-08-26T00:00:00Z',text:'ALFA evidencia sem snapshot sintetico.',
      title:'Runtime provenance guard',locator:'runtime://provenance/no-snapshot'
    }
  }]}})
});

const retrieval=require(path.join(tmp,'retrieval.js'));
(async()=>{
  const result=await retrieval.retrieveEvidence('tenant-a','ALFA evidencia',{
    domains:['runtime-ai'],includePublic:false,expandContext:false,knowledgeStatuses:['CONFIRMED']
  });
  assert.equal(result.items.length,1);
  assert.deepEqual(result.sourceSnapshotIds,[],'absent snapshot must remain absent');
  assert.equal(result.sourceSnapshotIds.includes('null'),false,'null must never become a provenance identifier');

  const knowledgeAt='2026-08-26T12:00:00Z';
  const withNull=retrieval.pinnedRetrievalCacheKey('tenant-a','ALFA',{sourceSnapshotIds:[null,undefined,'snap-1'],knowledgeAt});
  const clean=retrieval.pinnedRetrievalCacheKey('tenant-a','ALFA',{sourceSnapshotIds:['snap-1'],knowledgeAt});
  assert.equal(withNull,clean,'null/undefined inputs must not alter pinned cache identity');

  console.log('v20 AI provenance identifiers exclude null/undefined values OK');
})().catch(error=>{console.error(error);process.exit(1)});
