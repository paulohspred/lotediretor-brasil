const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const src=fs.readFileSync(path.join(root,'services/platform-api/src/municipality/v20-governance.ts'),'utf8');
const out=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},reportDiagnostics:true});
assert.equal((out.diagnostics||[]).filter(x=>x.category===ts.DiagnosticCategory.Error).length,0);
const tmp=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'ld-municipality-v20-')),'governance.js');fs.writeFileSync(tmp,out.outputText);const g=require(tmp);

assert.equal(g.MUNICIPAL_V20_VERSION,'municipality-governance-v20.2');
const permissions=g.effectivePermissions([{role:'DATA_STEWARD',status:'ACTIVE',permission_overrides:['custom.permission']},{role:'VIEWER',status:'REVOKED'}]);
assert(permissions.includes('dataset.publish'));assert(permissions.includes('dataset.rollback'));assert(permissions.includes('custom.permission'));assert(!permissions.includes('municipality.manage'));
assert.equal(g.publicationGate({snapshot_status:'VALIDATED',action:'PUBLISH',source_snapshot_id:'s1',permissions,actor:'u1',reason:'approved QA'}).status,'READY');
assert.equal(g.publicationGate({snapshot_status:'DRAFT',action:'PUBLISH',source_snapshot_id:'s1',permissions,actor:'u1',reason:'x'}).status,'BLOCKED');
assert.equal(g.publicationGate({snapshot_status:'SUPERSEDED',action:'ROLLBACK',source_snapshot_id:'s1',target_snapshot_id:'x',permissions,actor:'u1',reason:'rollback'}).status,'READY');
assert.equal(g.publicationGate({snapshot_status:'VALIDATED',action:'ROLLBACK',source_snapshot_id:'s1',target_snapshot_id:'x',permissions,actor:'u1',reason:'rollback'}).status,'BLOCKED');
assert.equal(g.licensingDecisionGuard({permissions:['license.review'],evidence_ids:['e1'],reviewer:'human',reason:'evidence reviewed',decision:'APPROVED',automated_decision_requested:true}).status,'BLOCKED_AUTOMATION');
assert.equal(g.licensingDecisionGuard({permissions:['license.review'],evidence_ids:['e1'],reviewer:'human',reason:'evidence reviewed',decision:'APPROVED'}).status,'READY_FOR_HUMAN_RECORD');
assert.equal(g.licensingDecisionGuard({permissions:['license.review'],evidence_ids:[],reviewer:'human',reason:'x',decision:'APPROVED'}).status,'HUMAN_REVIEW_REQUIRED');

const acl=g.buildInstitutionalAcl({permissions:['dataset.read','ai.retrieve'],subject_id:'alice',roles:['LEGAL_REVIEWER'],municipality_ibge:'3550308',datasets:[
  {id:'d1',visibility:'RESTRICTED',snapshot_status:'PUBLISHED',source_snapshot_id:'s1',acl:[{principal_kind:'ROLE',principal_value:'LEGAL_REVIEWER',permissions:['READ']}]},
  {id:'d2',visibility:'RESTRICTED',snapshot_status:'PUBLISHED',source_snapshot_id:'s2',acl:[{principal_kind:'SUBJECT',principal_value:'bob',permissions:['READ']}]},
  {id:'d3',visibility:'OPEN',snapshot_status:'PUBLISHED',source_snapshot_id:'s3',acl:[]},
  {id:'d4',visibility:'OPEN',snapshot_status:'VALIDATED',source_snapshot_id:'s4',acl:[]}
]});
assert.deepEqual(acl.dataset_ids,['d1','d3']);assert.deepEqual(acl.source_snapshot_ids,['s1','s3']);
const denied=g.buildInstitutionalAcl({permissions:['dataset.read'],subject_id:'alice',roles:[],datasets:[]});assert.equal(denied.status,'FORBIDDEN');assert.equal(denied.source_snapshot_ids.length,0);
assert.equal(g.openDataProjection({dataset_code:'CTM',title:'CTM',kind:'CTM',visibility:'OPEN',status:'ACTIVE'},{status:'PUBLISHED',base_date:'2026-08-25',source_snapshot_id:'s1'}).status,'PUBLIC');
assert.equal(g.openDataProjection({dataset_code:'CTM',visibility:'INTERNAL',status:'ACTIVE'},{status:'PUBLISHED'}).status,'NOT_PUBLIC');
const manifest=g.exportManifest({municipality_ibge:'3550308',generated_at:'2026-08-25T00:00:00Z',datasets:[{dataset_code:'B',kind:'GIS',visibility:'OPEN',status:'ACTIVE'},{dataset_code:'A',kind:'LEGAL',visibility:'INTERNAL',status:'ACTIVE'}],counts:{datasets:2}});
assert.deepEqual(manifest.datasets.map(x=>x.dataset_code),['A','B']);assert(manifest.excludes.includes('provider_credentials'));assert(!JSON.stringify(manifest).includes('secret_ref'));

const migrations=[200,201,202,203,204,205,206].map(n=>fs.readFileSync(path.join(root,'db/platform/migrations',`${n}_v20_municipality_${({200:'operational',201:'open_data_guard',202:'materialized_export',203:'legacy_rls',204:'publication_guard',205:'iptu_provenance',206:'open_records_policy'})[n]}.sql`),'utf8')).join('\n');
for(const token of ['municipality.department','municipality.member_role','municipality.dataset_snapshot','municipality.publication_event_v20','municipality.recalculation_job','municipality.itbi_record','municipality.licensing_case','municipality.export_job','FORCE ROW LEVEL SECURITY','open_dataset_read','municipality_tenant_organization_is_immutable','rollback_requires_previously_published_snapshot','source_snapshot_id','open_ctm_read','open_iptu_read'])assert(migrations.includes(token),token);
const controller=fs.readFileSync(path.join(root,'services/platform-api/src/municipality/municipality-v20.controller.ts'),'utf8');
for(const token of ['AI_GATEWAY_INTERNAL_URL','publicationGate({snapshot_status:target.status','affectedPropertyCount','recalculationJobs','recalculations/reconcile','licensingDecisionGuard','buildInstitutionalAcl','sourceSnapshotIds','knowledgeStatuses:[\'CONFIRMED\']','IPTU_RECORDED','CTM_UPSERT'])assert(controller.includes(token),token);
console.log('v20 Prefeitura governance/publication/RBAC/ACL contracts OK');
