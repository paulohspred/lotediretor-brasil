const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const src=fs.readFileSync(path.join(root,'services/platform-api/src/condo/v20-governance.ts'),'utf8');
const out=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true},reportDiagnostics:true});
assert.equal((out.diagnostics||[]).filter(x=>x.category===ts.DiagnosticCategory.Error).length,0);
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ld-condo-v20-'));fs.writeFileSync(path.join(tmp,'gov.js'),out.outputText);const gov=require(path.join(tmp,'gov.js'));

const parsed=gov.parseClauseLayout('doc-1',[
  {page:2,block_id:'b3',text:'continuação da obrigação',bbox:[0,20,100,30]},
  {page:1,block_id:'b1',text:'Cláusula 1 Uso das áreas comuns',bbox:[0,0,100,10]},
  {page:1,block_id:'b2',text:'É vedado...',bbox:[0,10,100,20]},
  {page:2,block_id:'b4',text:'Art. 2 Obras exigem aprovação',bbox:[0,30,100,40]},
]);
assert.equal(parsed.status,'PARSED_CANDIDATES');assert.equal(parsed.clauses.length,2);assert.deepEqual(parsed.clauses[0].citations.map(x=>x.page),[1,1,2]);assert.equal(parsed.clauses[0].status,'CANDIDATE');

let rules=gov.resolveRuleSet([
  {id:'old',parameter:'PETS',value:'NO',status:'CONFIRMED',precedence:10,effective_from:'2020-01-01',effective_to:'2024-01-01'},
  {id:'low',parameter:'PETS',value:'NO',status:'CONFIRMED',precedence:10,effective_from:'2024-01-01'},
  {id:'high',parameter:'PETS',value:'YES_WITH_RULES',status:'CONFIRMED',precedence:20,effective_from:'2024-01-01'},
  {id:'candidate',parameter:'PETS',value:'ANY',status:'CANDIDATE',precedence:99,effective_from:'2024-01-01'},
],'2026-08-25');
assert.equal(rules.status,'RESOLVED');assert.equal(rules.resolved[0].rule.id,'high');
rules=gov.resolveRuleSet([
  {id:'a',parameter:'PARKING',value:'A',status:'CONFIRMED',precedence:20,effective_from:'2020-01-01'},
  {id:'b',parameter:'PARKING',value:'B',status:'CONFIRMED',precedence:20,effective_from:'2020-01-01'},
],'2026-08-25');
assert.equal(rules.status,'CONFLICTING');assert.deepEqual(rules.conflicts[0].rule_ids,['a','b']);

const ballot=gov.evaluateBallot({eligible_subject_hashes:['u1','u2','u3'],quorum:{min_present:2,min_participation_fraction:.5,min_approval_fraction:.5},votes:[
  {subject_hash:'u1',choice:'FOR',signature_status:'VERIFIED'},
  {subject_hash:'u2',choice:'AGAINST',signature_status:'VERIFIED'},
  {subject_hash:'u2',choice:'FOR',signature_status:'VERIFIED'},
  {subject_hash:'u3',choice:'FOR',signature_status:'PENDING'},
  {subject_hash:'outsider',choice:'FOR',signature_status:'VERIFIED'},
]});
assert.equal(ballot.status,'CALCULATED_NOT_ENACTED');assert.equal(ballot.present,2);assert.equal(ballot.approved,true);assert.equal(ballot.rejected.length,3);assert(ballot.rejected.some(x=>x.reasons.includes('DUPLICATE_VOTE')));assert(ballot.rejected.some(x=>x.reasons.includes('SIGNATURE_NOT_VERIFIED')));assert(ballot.rejected.some(x=>x.reasons.includes('NOT_ELIGIBLE')));

assert.equal(gov.sanctionGuard({rule_status:'CONFIRMED',evidence_ids:['e1'],automated_decision_requested:true}).status,'BLOCKED_AUTOMATION');
assert.equal(gov.sanctionGuard({rule_status:'CANDIDATE',evidence_ids:[],automated_decision_requested:false}).status,'BLOCKED_MISSING_GROUNDS');
assert.equal(gov.sanctionGuard({rule_status:'CONFIRMED',evidence_ids:['e1'],human_decision:'APPROVE',human_reviewer:'manager',decision_reason:'evidence',defense_status:'SUBMITTED'}).status,'DEFENSE_DUE_PROCESS_REQUIRED');
assert.equal(gov.sanctionGuard({rule_status:'CONFIRMED',evidence_ids:['e1'],human_decision:'APPROVE',human_reviewer:'manager',decision_reason:'evidence',defense_status:'RESOLVED'}).status,'READY_FOR_MANUAL_ISSUANCE');

const changes=gov.legalChangeDiff([{id:'r1',v:1},{id:'removed',v:1}],[{id:'r1',v:2},{id:'added',v:1}]);assert.equal(changes.events.length,3);assert(changes.events.every(x=>x.status==='CANDIDATE_REVIEW'));
const summary=gov.buildExternalSummary({mode:'BROKER',condominium:{id:'c1',name:'Condo',municipality_ibge:'3550308'},property_id:'p1',aitec_project_id:'a1',rules:[{id:'r1',status:'CONFIRMED',parameter:'WORK',value:'REVIEW',source_locator:'p.3',evidence_ids:['e1']},{id:'r2',status:'CANDIDATE',parameter:'SECRET',value:'X'}]});assert.equal(summary.rules.length,1);assert(summary.redacted.includes('private_documents'));assert.equal(summary.property_id,'p1');
const aclA=gov.buildRetrievalAcl('tenant-a','condo-1',['doc-a','doc-a']);const aclB=gov.buildRetrievalAcl('tenant-b','condo-1',['doc-b']);assert.deepEqual(aclA.allowed_document_ids,['doc-a']);assert.notDeepEqual(aclA.opensearch_filter,aclB.opensearch_filter);assert(JSON.stringify(aclA.opensearch_filter).includes('tenant-a'));assert(!JSON.stringify(aclA.opensearch_filter).includes('doc-b'));
const empty=gov.buildRetrievalAcl('tenant-a','condo-1',[]);assert(JSON.stringify(empty.opensearch_filter).includes('__NO_DOCUMENT_ACCESS__'));

const migration=fs.readFileSync(path.join(root,'db/platform/migrations/199_v20_condo_operational.sql'),'utf8');for(const token of ['condo.document_clause','condo.rule_relation','condo.ballot','condo.ballot_vote','condo.signature_envelope','condo.sanction_case','condo.defense','condo.charge','condo.communication_endpoint','condo.legal_monitor_event','condo.integration_link','condo.retrieval_acl','FORCE ROW LEVEL SECURITY',"status <> 'ISSUED'"])assert(migration.includes(token),token);
const controller=fs.readFileSync(path.join(root,'services/platform-api/src/condo/condo-v20.controller.ts'),'utf8');for(const token of ['parseClauseLayout','evaluateBallot','sanctionGuard','buildRetrievalAcl','NO_AUTHORIZED_DOCUMENTS','/ai/v1/retrieve','documentIds:docs','includePublic:false'])assert(controller.includes(token),token);
const ops=fs.readFileSync(path.join(root,'services/platform-api/src/condo/condo-v20-ops.controller.ts'),'utf8');for(const token of ['defenses/:defenseId/review','store_secret_by_reference_only','recipient_ref_hash','legal-monitor-events/:eventId/review'])assert(ops.includes(token),token);
console.log('v20 Condomínio 360 governance/ACL guardrail gate OK');
