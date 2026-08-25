const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ld-ai-reranker-v20-'));
function compile(rel,name){
  const src=fs.readFileSync(path.join(root,rel),'utf8');
  const out=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
  const dst=path.join(tmp,name);fs.writeFileSync(dst,out);return dst;
}
compile('services/ai-gateway/src/embeddings.ts','embeddings.js');
compile('services/ai-gateway/src/retrieval.ts','retrieval.js');
compile('services/ai-gateway/src/evals.ts','evals.js');

process.env.OPENSEARCH_URL='http://opensearch.test:9200';
process.env.OPENSEARCH_EVIDENCE_INDEX='evidence-reranker-test';
delete process.env.AI_EMBEDDINGS_ENDPOINT;
delete process.env.AI_EMBEDDINGS_MODEL;
delete process.env.AI_EMBEDDINGS_API_KEY;
delete process.env.AI_API_KEY;

const corpus=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/ai-reranker-golden-v20.json'),'utf8'));
assert.equal(corpus.truthClass,'SYNTHETIC_RETRIEVAL_ONLY');
assert.equal(corpus.municipalTruth,false);
assert(corpus.cases.length>=5);
const byQuery=new Map(corpus.cases.map(x=>[x.query,x]));

global.fetch=async(_url,options={})=>{
  const body=JSON.parse(options.body||'{}');
  const query=body?.query?.bool?.must?.[0]?.multi_match?.query;
  const testCase=byQuery.get(query);
  if(!testCase)throw new Error(`unexpected query ${query}`);
  return{
    ok:true,
    status:200,
    json:async()=>({hits:{hits:testCase.rawHits.map((hit,index)=>({
      _id:hit.id,
      _score:hit.score-index/1000,
      _source:{
        tenant_id:'tenant-a',domain:'synthetic',document_id:`doc-${testCase.id}`,
        document_version_id:'dv-synthetic',source_snapshot_id:'snap-synthetic',chunk_index:index,
        visibility:'PRIVATE',knowledge_status:'CONFIRMED',recorded_at:'2026-01-01T00:00:00Z',
        text:hit.text,title:hit.title,locator:hit.locator,section_id:hit.sectionId
      }
    }))}})
  };
};

const retrieval=require(path.join(tmp,'retrieval.js'));
const evals=require(path.join(tmp,'evals.js'));

(async()=>{
  const metrics=[];
  for(const testCase of corpus.cases){
    assert.notEqual(testCase.rawHits[0].id,testCase.relevantEvidenceIds[0],`${testCase.id}: fixture must require reranking`);
    const result=await retrieval.retrieveEvidence('tenant-a',testCase.query,{
      includePublic:false,
      expandContext:false,
      topK:3,
      knowledgeAt:'2026-08-25T00:00:00Z',
      sourceSnapshotIds:['snap-synthetic']
    });
    const retrievedIds=result.items.map(x=>x.id);
    assert.equal(result.mode,'lexical_legal_rerank',`${testCase.id}: mode`);
    assert.equal(retrievedIds[0],testCase.relevantEvidenceIds[0],`${testCase.id}: relevant evidence must be reranked first`);
    metrics.push(evals.rankingMetrics(retrievedIds,testCase.relevantEvidenceIds,3));
  }

  const aggregate={
    recallAtK:metrics.reduce((a,x)=>a+x.recallAtK,0)/metrics.length,
    mrr:metrics.reduce((a,x)=>a+x.mrr,0)/metrics.length,
    ndcgAtK:metrics.reduce((a,x)=>a+x.ndcgAtK,0)/metrics.length
  };
  for(const key of ['recallAtK','mrr','ndcgAtK']){
    assert(aggregate[key]>=corpus.thresholds[key],`${key}=${aggregate[key]} threshold=${corpus.thresholds[key]}`);
  }
  console.log('v20 AI legal reranker golden eval OK',aggregate);
})().catch(error=>{console.error(error);process.exit(1)});
