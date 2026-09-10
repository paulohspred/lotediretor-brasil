const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const src=fs.readFileSync(path.join(root,'services/control-api/src/v20-admin-logic.ts'),'utf8');
const js=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const tmp=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'ld-admin-v20-')),'logic.js');fs.writeFileSync(tmp,js);
const g=require(tmp);

const now=new Date('2026-08-25T12:00:00Z');
const d1=g.dunningPolicy(0,now);assert.equal(d1.status,'RETRY_SCHEDULED');assert.equal(d1.attempt,1);assert.equal(d1.delayDays,1);
assert.equal(g.dunningPolicy(4,now).status,'EXHAUSTED');
assert.equal(g.refundGuard({paymentStatus:'PAID',paymentAmountCents:10000,requestedCents:3000,alreadyAdjustedCents:2000}).status,'READY');
assert.equal(g.refundGuard({paymentStatus:'PAID',paymentAmountCents:10000,requestedCents:9000,alreadyAdjustedCents:2000}).status,'BLOCKED');
assert.equal(g.chargebackGuard({paymentStatus:'APPROVED',paymentAmountCents:10000,alreadyAdjustedCents:2500}).amountCents,7500);

const invoice=g.invoiceTotals([{description:'plan',quantity:1,unitCents:10000},{description:'usage',quantity:2,unitCents:1500}],{kind:'PERCENT',value:10});
assert.equal(invoice.subtotalCents,13000);assert.equal(invoice.discountCents,1300);assert.equal(invoice.totalCents,11700);

const support=g.supportSessionGate({requestedBy:'maker',approvedBy:'checker',scopes:['READ_DATA','IMPERSONATE_USER'],targetSubject:'user-1',reason:'ticket 123',now:'2026-08-25T12:00:00Z',expiresAt:'2026-08-25T13:00:00Z'});assert.equal(support.status,'READY');
assert.equal(g.supportSessionGate({requestedBy:'same',approvedBy:'same',scopes:['READ_DATA'],reason:'x',now:'2026-08-25T12:00:00Z',expiresAt:'2026-08-25T13:00:00Z'}).reason,'maker_checker_violation');
assert.equal(g.supportSessionGate({requestedBy:'a',approvedBy:'b',scopes:['READ_DATA'],reason:'x',now:'2026-08-25T12:00:00Z',expiresAt:'2026-08-25T17:00:00Z'}).reason,'support_session_ttl_exceeds_4h');

const a1=g.experimentAssignment({tenantId:'t1',experimentId:'e1',subjectHash:'s1',variants:['A','B'],allocationPercent:100});
const a2=g.experimentAssignment({tenantId:'t1',experimentId:'e1',subjectHash:'s1',variants:['A','B'],allocationPercent:100});assert.deepEqual(a1,a2);assert.equal(a1.assigned,true);assert(['A','B'].includes(a1.variant));
const f1=g.featureRollout({tenantId:'t1',flagCode:'new-ui',enabled:true,variant:'V2',rolloutPercent:37});const f2=g.featureRollout({tenantId:'t1',flagCode:'new-ui',enabled:true,variant:'V2',rolloutPercent:37});assert.deepEqual(f1,f2);
assert.equal(g.aiCostMicros({inputTokens:1000,outputTokens:500,inputRateMicrosPerMillion:2000000,outputRateMicrosPerMillion:6000000}),5000);
assert.equal(g.reconciliation({paymentNetCents:10000,adjustmentCents:1000,ledgerCents:9000}).status,'BALANCED');
assert.equal(g.reconciliation({paymentNetCents:10000,adjustmentCents:1000,ledgerCents:8999}).status,'DIFFERENCE');
assert.equal(g.nfseGuard({tenantId:'t1',invoiceId:'i1',requestedBy:'admin'}).status,'REQUESTED');
assert.equal(g.nfseGuard({applicable:false}).status,'NOT_APPLICABLE');

const migrations=['200_v20_admin_saas_operational.sql','201_v20_admin_saas_analytics.sql','202_v20_admin_append_only_replay.sql'].map(x=>fs.readFileSync(path.join(root,'db/control/migrations',x),'utf8')).join('\n');
for(const token of ['admin.idempotency_record','catalog.service_contract','catalog.add_on_version','catalog.coupon','billing.invoice','billing.dunning_case','billing.adjustment','billing.reconciliation_run','billing.payment_allocation','fiscal.nfse_document','support.support_session','support.impersonation_event','cms.media_asset','cms.redirect','cms.form_submission','product.analytics_event','product.funnel_definition','product.experiment','product.feature_flag_target','ai_ops.usage_cost','release.rollback_event','ops.backup_run','ops.restore_run','ops.dr_drill','FORCE ROW LEVEL SECURITY','append_only_guard'])assert(migrations.includes(token),token);
const controller=fs.readFileSync(path.join(root,'services/control-api/src/v20-admin.controller.ts'),'utf8');
for(const token of ['idempotency_key_required','maker_checker_violation','SUPPORT_SESSION_STARTED','billing/payment','billing.reconcile','fiscal/nfse','analytics/funnels','analytics/experiments','featureRollout','ROLLBACK_EXECUTED','ai-ops/usage','ops/backups','ops/restores','ops/dr-drills'])assert(controller.includes(token),token);
assert(controller.includes("set_config('app.control_admin','true',true)"));
const rls=fs.readFileSync(path.join(root,'ops/rls/runtime-isolation.sh'),'utf8');
for(const token of ['CONTROL_DB_APP_USER','property360.property','aitec.job','support.customer_success_account','cross tenant write unexpectedly succeeded','control cross tenant write unexpectedly succeeded'])assert(rls.includes(token),token);
const backup=fs.readFileSync(path.join(root,'ops/backup/backup.sh'),'utf8');const restore=fs.readFileSync(path.join(root,'ops/backup/restore-drill.sh'),'utf8');assert(backup.includes('ops.backup_run'));assert(restore.includes('ops.restore_run'));assert(restore.includes('ops.dr_drill'));
console.log('v20 Admin SaaS financial/support/analytics/ops contracts OK');
