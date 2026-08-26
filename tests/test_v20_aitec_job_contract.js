const fs=require('fs');

const controller=fs.readFileSync('services/platform-api/src/aitec/aitec-jobs.controller.ts','utf8');
const moduleFile=fs.readFileSync('services/platform-api/src/aitec/aitec.module.ts','utf8');
const app=fs.readFileSync('services/platform-api/src/app.module.ts','utf8');
const browser=fs.readFileSync('tests/browser/aitec-job.spec.mjs','utf8');
const config=fs.readFileSync('tests/browser/playwright.config.mjs','utf8');
const worker=fs.readFileSync('workers/aitec/main.py','utf8');
const migration=fs.readFileSync('db/platform/migrations/213_v20_aitec_jobs.sql','utf8');
const retryMigration=fs.readFileSync('db/platform/migrations/214_v20_aitec_job_retry_schedule.sql','utf8');
const prometheus=fs.readFileSync('infra/prometheus/prometheus.yml','utf8');
const rules=fs.readFileSync('infra/prometheus/rules/lotediretor.yml','utf8');
const resilience=fs.readFileSync('ops/resilience/runtime-fault-injection.sh','utf8');

for(const needle of [
  "@Controller('api/v1/aitec')",
  "@Post('projects/:projectId/jobs')",
  "@Get('jobs/:jobId')",
  "module_not_entitled",
  "idempotency_key_required",
  "withIdempotency(pool,s.organizationId,'aitec.v20.job'",
  "insert into aitec.job",
  "status,attempts,execution_context,next_attempt_at",
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
  'ADD COLUMN IF NOT EXISTS next_attempt_at',
  'aitec_job_ready_idx',
  "WHERE status='QUEUED'",
]){
  if(!retryMigration.includes(needle))throw new Error(`A.I TEC retry migration missing contract: ${needle}`);
}
for(const needle of [
  "where status='QUEUED' and next_attempt_at <= now()",
  'for update skip locked',
  "set status='RUNNING'",
  "set status='COMPLETED'",
  'retry_delay_seconds',
  'next_attempt_at=case when',
  'aitec.job.completed',
  'aitec.job.failed',
  'aitec_engine_context_mismatch',
  'aitec_engine_constraint_context_mismatch',
  'worker_stale_requeued',
  'lotediretor_aitec_jobs',
  'lotediretor_aitec_oldest_job_age_seconds',
  'lotediretor_aitec_worker_last_db_success_unixtime',
]){
  if(!worker.includes(needle))throw new Error(`A.I TEC worker missing contract: ${needle}`);
}
if(!moduleFile.includes('AitecJobsController'))throw new Error('AitecModule must register AitecJobsController');
if(!app.includes("import {AitecModule}"))throw new Error('AppModule must import AitecModule');
if(!app.includes('EntitlementSyncModule,AitecModule'))throw new Error('AppModule must register AitecModule');
for(const needle of ['terrain.tin','Idempotency-Key','QUEUED','RUNNING','next_attempt_at','aitec-terrain-v20.1','professional_review_required','engine_response','triangle_count']){
  if(!browser.includes(needle))throw new Error(`browser A.I TEC job journey missing: ${needle}`);
}
if(!config.includes('/aitec-job\\.spec\\.mjs/'))throw new Error('Playwright config must include A.I TEC job journey');
for(const needle of ['job_name: aitec-worker',"targets: ['aitec-worker:9104']"]){
  if(!prometheus.includes(needle))throw new Error(`Prometheus missing A.I TEC worker scrape contract: ${needle}`);
}
for(const needle of ['LoteDiretorAitecWorkerDown','LoteDiretorAitecQueueStalled','LoteDiretorAitecJobFailures','LoteDiretorAitecRetryStorm']){
  if(!rules.includes(needle))throw new Error(`Prometheus rules missing A.I TEC alert: ${needle}`);
}
for(const needle of ['retry_scheduled_without_hot_loop','recovered_same_job_completed_once','completion_events']){
  if(!resilience.includes(needle))throw new Error(`A.I TEC resilience drill missing: ${needle}`);
}
console.log('v20 authenticated durable A.I TEC job + retry + telemetry + resilience contract gate OK');
