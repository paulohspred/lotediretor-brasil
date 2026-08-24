const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ld-legal-temporal-v20-'));
const src=fs.readFileSync(path.join(root,'services/platform-api/src/territorial/legal-temporal-runtime.ts'),'utf8');
const out=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;
fs.writeFileSync(path.join(tmp,'legal-temporal-runtime.js'),out);
const {resolveLegalTemporalGraph}=require(path.join(tmp,'legal-temporal-runtime.js'));

const versions=[
  {id:'v-old',document_id:'law',valid_from:'2020-01-01'},
  {id:'v-new',document_id:'amend',valid_from:'2024-01-01'},
];

let r=resolveLegalTemporalGraph(versions,[
  {id:'rev',from_document_version_id:'v-new',to_document_version_id:'v-old',relation_type:'REVOGA',valid_from:'2024-06-01',status:'CONFIRMED'},
],'2024-05-31');
assert.equal(r.versions['v-old'].state,'ACTIVE');

r=resolveLegalTemporalGraph(versions,[
  {id:'rev',from_document_version_id:'v-new',to_document_version_id:'v-old',relation_type:'REVOGA',valid_from:'2024-06-01',status:'CONFIRMED'},
],'2024-06-01');
assert.equal(r.versions['v-old'].state,'INACTIVE');
assert(r.versions['v-old'].reasons.some(x=>x.startsWith('terminal_off:')));

r=resolveLegalTemporalGraph(versions,[
  {id:'suspend',from_document_version_id:'v-new',to_document_version_id:'v-old',relation_type:'SUSPENDE_EFICACIA',valid_from:'2024-02-01',status:'CONFIRMED'},
  {id:'restore',from_document_version_id:'v-new',to_document_version_id:'v-old',relation_type:'RESTAURA_EFICACIA',valid_from:'2024-03-01',status:'CONFIRMED'},
],'2024-02-15');
assert.equal(r.versions['v-old'].state,'INACTIVE');

r=resolveLegalTemporalGraph(versions,[
  {id:'suspend',from_document_version_id:'v-new',to_document_version_id:'v-old',relation_type:'SUSPENDE_EFICACIA',valid_from:'2024-02-01',status:'CONFIRMED'},
  {id:'restore',from_document_version_id:'v-new',to_document_version_id:'v-old',relation_type:'RESTAURA_EFICACIA',valid_from:'2024-03-01',status:'CONFIRMED'},
],'2024-03-15');
assert.equal(r.versions['v-old'].state,'ACTIVE');

r=resolveLegalTemporalGraph(versions,[
  {id:'article-revoke',from_document_version_id:'v-new',to_document_version_id:'v-old',target_article_id:'art-12',relation_type:'REVOGA',valid_from:'2024-06-01',status:'CONFIRMED'},
],'2024-07-01');
assert.equal(r.versions['v-old'].state,'ACTIVE');
assert.equal(r.articles['art-12'].state,'INACTIVE');

r=resolveLegalTemporalGraph(versions,[
  {id:'s1',from_document_version_id:'v-new',to_document_version_id:'v-old',relation_type:'SUSPENDE_EFICACIA',valid_from:'2024-02-01',status:'CONFIRMED'},
  {id:'r1',from_document_version_id:'v-new',to_document_version_id:'v-old',relation_type:'RESTAURA_EFICACIA',valid_from:'2024-02-01',status:'CONFIRMED'},
],'2024-02-02');
assert.equal(r.versions['v-old'].state,'CONFLICTING');
assert.equal(r.conflicts.length,1);

r=resolveLegalTemporalGraph(versions,[
  {id:'candidate-revoke',from_document_version_id:'v-new',to_document_version_id:'v-old',relation_type:'REVOGA',valid_from:'2024-02-01',status:'CANDIDATE'},
],'2024-03-01');
assert.equal(r.versions['v-old'].state,'ACTIVE');
assert.deepEqual(r.pendingRelationIds,['candidate-revoke']);

r=resolveLegalTemporalGraph(versions,[
  {id:'undated-revoke',from_document_version_id:'v-new',to_document_version_id:'v-old',relation_type:'REVOGA',status:'CONFIRMED'},
],'2024-03-01');
assert.equal(r.versions['v-old'].state,'UNKNOWN');
assert(r.unknownRelationIds.includes('undated-revoke'));

r=resolveLegalTemporalGraph(versions,[
  {id:'rev',from_document_version_id:'v-new',to_document_version_id:'v-old',relation_type:'REVOGA',valid_from:'2024-02-01',status:'CONFIRMED'},
  {id:'restore-after-revoke',from_document_version_id:'v-new',to_document_version_id:'v-old',relation_type:'RESTAURA_EFICACIA',valid_from:'2024-03-01',status:'CONFIRMED'},
],'2024-04-01');
assert.equal(r.versions['v-old'].state,'CONFLICTING');
assert(r.conflicts.some(x=>x.reason==='restore_after_terminal_revocation'));

r=resolveLegalTemporalGraph([{id:'future',valid_from:'2027-01-01'}],[],'2026-01-01');
assert.equal(r.versions.future.state,'INACTIVE');

console.log('v20 legal temporal runtime OK');
