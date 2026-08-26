const fs=require('fs');

const controller=fs.readFileSync('services/platform-api/src/aitec/aitec-jobs.controller.ts','utf8');
const moduleFile=fs.readFileSync('services/platform-api/src/aitec/aitec.module.ts','utf8');
const app=fs.readFileSync('services/platform-api/src/app.module.ts','utf8');
const browser=fs.readFileSync('tests/browser/aitec-job.spec.mjs','utf8');
const config=fs.readFileSync('tests/browser/playwright.config.mjs','utf8');

for(const needle of [
  "@Controller('api/v1/aitec')",
  "@Post('projects/:projectId/jobs')",
  "@Get('jobs/:jobId')",
  "module_not_entitled",
  "withIdempotency(pool,s.organizationId,'aitec.v20.job'",
  "where id=$1 and tenant_id=$2",
  "where s.id=$1 and s.tenant_id=$2",
  "/aitec/v20/execute/",
  "status='QUEUED'",
  "status='COMPLETED'",
  "STUDY_PREPROJECT_NOT_EXECUTIVE",
]){
  if(!controller.includes(needle))throw new Error(`A.I TEC job controller missing contract: ${needle}`);
}
if(!moduleFile.includes('AitecJobsController'))throw new Error('AitecModule must register AitecJobsController');
if(!app.includes("import {AitecModule}"))throw new Error('AppModule must import AitecModule');
if(!app.includes('EntitlementSyncModule,AitecModule'))throw new Error('AppModule must register AitecModule');
for(const needle of ['terrain.tin','Idempotency-Key','aitec-terrain-v20.1','professional_review_required','triangle_count']){
  if(!browser.includes(needle))throw new Error(`browser A.I TEC job journey missing: ${needle}`);
}
if(!config.includes('/aitec-job\\.spec\\.mjs/'))throw new Error('Playwright config must include A.I TEC job journey');
console.log('v20 authenticated persisted A.I TEC job contract gate OK');
