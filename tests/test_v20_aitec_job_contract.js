const fs=require('fs');

const controller=fs.readFileSync('services/platform-api/src/aitec/aitec-jobs.controller.ts','utf8');
const moduleFile=fs.readFileSync('services/platform-api/src/aitec/aitec.module.ts','utf8');
const app=fs.readFileSync('services/platform-api/src/app.module.ts','utf8');
const browser=fs.readFileSync('tests/browser/aitec-job.spec.mjs','utf8');
const config=fs.readFileSync('tests/browser/playwright.config.mjs','utf8');
const worker=fs.readFileSync('workers/aitec/main.py','utf8');
const migration=fs.readFileSync('db/platform/migrations/213_v20_aitec_jobs.sql','utf8');

for(const needle of [
  "@Controller('api/v1/aitec')",
  "@Post('projects/:projectId/jobs')",
  "@Get('jobs/:jobId')",
  "module_not_entitled",
  "idempotency_key_required",
  "withIdempotency(pool,s.organizationId,'aitec.v20.job'",
  "insert into aitec.job",
  "status,attempts,execution_context",
  "aitec.job.queued",
  "where j.id=$1 and j.tenant_id=$2",
  "AITEC_JOB_OPERATIONS",
  "aitec_job_payload_too_large",
]){
  if(!controller.includes(needle))throw new Error(`A.I TEC job controller missing contract: ${needle}`);
}
for(const needle of [
  'CREATE TABLE IF NOT EXISTS aitec.job',
  "CHECK(status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED'))",
  'FOREIGN KEY(tenant_id,project_id)',
  'ALTER TABLE aitec.job FORCE ROW LEVEL SECURITY',
]){
  if(!migration.includes(needle))throw new Error(`A.I TEC job migration missing contract: ${needle}`);
}
for(const needle of [
  "where status='QUEUED'",
  'for update skip locked',
  "set status='RUNNING'",
  "set status='COMPLETED'",
  'aitec.job.completed',
  'aitec.job.failed',
  'aitec_engine_context_mismatch',
  'aitec_engine_constraint_context_mismatch',
  'worker_stale_requeued',
]){
  if(!worker.includes(needle))throw new Error(`A.I TEC worker missing contract: ${needle}`);
}
if(!moduleFile.includes('AitecJobsController'))throw new Error('AitecModule must register AitecJobsController');
if(!app.includes("import {AitecModule}"))throw new Error('AppModule must import AitecModule');
if(!app.includes('EntitlementSyncModule,AitecModule'))throw new Error('AppModule must register AitecModule');
for(const needle of ['terrain.tin','Idempotency-Key','QUEUED','RUNNING','aitec-terrain-v20.1','professional_review_required','engine_response','triangle_count']){
  if(!browser.includes(needle))throw new Error(`browser A.I TEC job journey missing: ${needle}`);
}
if(!config.includes('/aitec-job\\.spec\\.mjs/'))throw new Error('Playwright config must include A.I TEC job journey');
console.log('v20 authenticated durable A.I TEC job + worker contract gate OK');
