const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ld-property-rural-v20-'));
for(const [src,dst] of [
  ['services/platform-api/src/property360/v20-market.ts','market.js'],
  ['services/platform-api/src/rural/v20-readiness.ts','rural.js'],
]){
  const code=fs.readFileSync(path.join(root,src),'utf8');
  const out=ts.transpileModule(code,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true},reportDiagnostics:true});
  assert.equal((out.diagnostics||[]).filter(x=>x.category===ts.DiagnosticCategory.Error).length,0,src);
  fs.writeFileSync(path.join(tmp,dst),out.outputText);
}
const market=require(path.join(tmp,'market.js'));
const rural=require(path.join(tmp,'rural.js'));

const evidence={validation_status:'PASS',publication_status:'ACTIVE',license_terms:'licensed-test',source_sha256:'a'.repeat(64),source_date:'2026-08-01'};
const comparables=[
  {id:'c1',area_m2:100,price_cents:1000000,source_kind:'LICENSED',source_snapshot_id:'s1',observed_at:'2026-08-01',...evidence},
  {id:'c2',area_m2:100,price_cents:1100000,source_kind:'LICENSED',source_snapshot_id:'s2',observed_at:'2026-08-02',...evidence},
  {id:'c3',area_m2:100,price_cents:900000,source_kind:'OBSERVED',source_snapshot_id:'s3',observed_at:'2026-08-03',...evidence},
  {id:'demo',area_m2:100,price_cents:99999999,source_kind:'DEMO',source_snapshot_id:'sd',observed_at:'2026-08-04',...evidence},
];
const avm=market.estimateAvm(100,comparables,{version:'avm-v20-test',status:'APPROVED',min_comparables:3,max_age_days:60},'2026-08-25');
assert.equal(avm.status,'CALCULATED_FROM_APPROVED_METHOD_AND_REAL_EVIDENCE');
assert.equal(avm.estimate_cents,1000000);
assert.deepEqual(avm.comparable_ids,['c1','c2','c3']);
assert(avm.evidence.rejected.some(x=>x.id==='demo'&&x.reasons.includes('DEMO_SOURCE_FORBIDDEN')));
assert.equal(market.estimateAvm(100,comparables,{version:'draft',status:'DRAFT',min_comparables:3,max_age_days:60},'2026-08-25').status,'REQUIRES_CALIBRATION');
const broken=comparables.map(x=>({...x,validation_status:'FAIL'}));
assert.equal(market.estimateAvm(100,broken,{version:'v',status:'APPROVED',min_comparables:3,max_age_days:60},'2026-08-25').status,'REQUIRES_INPUT');

const velocity=market.marketVelocity([{period:'2026-08-01',units_sold:20,inventory_end:80,units_leased:5,rental_inventory_end:15}]);
assert.equal(velocity.items[0].vso,0.2);assert.equal(velocity.items[0].rental_absorption,0.25);
const ranked=market.rankLandCandidates([
  {id:'a',metrics:{area:100,price:100}},{id:'b',metrics:{area:120,price:150}},{id:'missing',metrics:{area:100}},{id:'hard',hard_invalid:true,metrics:{area:200,price:1}},
],{area:{weight:2,direction:'MAX'},price:{weight:1,direction:'MIN'}});
assert.equal(ranked.status,'RANKED');assert.equal(ranked.items[0].id,'b');assert(ranked.excluded.some(x=>x.id==='missing'));assert(ranked.excluded.some(x=>x.id==='hard'));

const complete=rural.RURAL_CONNECTOR_CODES.map((code,i)=>({code,registry_status:'CONFIGURED',access_mode:'API',legal_availability:'AUTHORIZED_TEST',source_id:`src-${i}`,run_status:'SUCCEEDED',source_snapshot_id:`snap-${i}`,source_sha256:'b'.repeat(64),source_date:'2026-08-25',validation_status:'PASS',publication_status:'ACTIVE',license_terms:'test-license',completed_at:'2026-08-25T12:00:00Z'}));
const matrix=rural.readinessMatrix(complete);assert.equal(matrix.status,'RUNTIME_EVIDENCE_COMPLETE');assert.equal(matrix.homologated,false);assert(matrix.items.every(x=>x.runtime_evidence_complete&&x.homologated===false));
const partial=rural.readinessMatrix(complete.slice(1));assert.equal(partial.status,'EXTERNAL_GATES_REMAIN');assert(partial.items.find(x=>x.code===rural.RURAL_CONNECTOR_CODES[0]).missing.length>0);
const pending=rural.recordGoldenReview({expected:{x:1},actual:{x:1}});assert.equal(pending.status,'PENDING_EXTERNAL_REVIEW');
const reviewed=rural.recordGoldenReview({expected:{x:1},actual:{x:1},reviewer:'reviewer',professional_reference:'ART/RRT/external-ref',reviewed_at:'2026-08-25T12:00:00Z'});assert.equal(reviewed.status,'EXTERNAL_REVIEW_RECORDED');assert.equal(reviewed.homologated,false);

const migration=fs.readFileSync(path.join(root,'db/platform/migrations/198_v20_property_rural_operational.sql'),'utf8');
for(const token of ['property360.avm_methodology','property360.market_series','property360.land_prospect_run','property360.b2b_api_key','resolve_b2b_api_key','rural.connector_catalog','rural.connector_config','rural.connector_run','rural.golden_case','SICOR_BACEN'])assert(migration.includes(token),token);
const pc=fs.readFileSync(path.join(root,'services/platform-api/src/property360/property360-v20.controller.ts'),'utf8');
for(const token of ['DEMO','source_snapshot_not_eligible_for_operational_market_use','estimateAvm','marketVelocity','rankLandCandidates','resolve_b2b_api_key','randomBytes'])assert(pc.includes(token),token);
const rc=fs.readFileSync(path.join(root,'services/platform-api/src/rural/rural-v20.controller.ts'),'utf8');
for(const token of ['connector_not_configured','EVIDENCE_INCOMPLETE','readinessMatrix','homologated:false','golden-cases'])assert(rc.includes(token),token);
console.log('v20 Imovel 360 + RE Rural operational implementation gate OK');
