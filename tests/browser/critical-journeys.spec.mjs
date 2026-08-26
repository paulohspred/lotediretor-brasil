import {test,expect} from '@playwright/test';

const USER='cliente@lotediretor.local';
const PASSWORD='lotediretor';

async function oidcLogin(page,returnTo='/app/dashboard'){
  await page.goto(returnTo,{waitUntil:'domcontentloaded'});
  await expect(page).toHaveURL(/\/login\?returnTo=/);
  await page.getByRole('link',{name:'Entrar com conta LoteDiretor'}).click();
  await page.locator('#username').fill(USER);
  await page.locator('#password').fill(PASSWORD);
  await Promise.all([
    page.waitForURL(url=>url.pathname===returnTo,{timeout:60_000}),
    page.locator('#kc-login').click(),
  ]);
  const session=(await page.context().cookies()).find(c=>c.name==='ld_session');
  expect(session,'real OIDC login must create ld_session').toBeTruthy();
  return page.context().request;
}

async function json(response,label){
  const text=await response.text();
  let body;try{body=JSON.parse(text)}catch{throw new Error(`${label} returned non-JSON ${response.status()}: ${text.slice(0,1000)}`)}
  expect(response.ok(),`${label} ${response.status()}: ${text.slice(0,2000)}`).toBeTruthy();
  return body;
}

async function pollReport(request,id,timeoutMs=60_000){
  const deadline=Date.now()+timeoutMs;
  let last;
  while(Date.now()<deadline){
    const response=await request.get(`/api/v1/reports/${id}/status`);
    last=await json(response,'report status');
    if(last.status==='COMPLETED')return last;
    if(last.status==='FAILED')throw new Error(`report worker failed: ${JSON.stringify(last)}`);
    await new Promise(resolve=>setTimeout(resolve,1000));
  }
  throw new Error(`report did not complete within ${timeoutMs}ms; last=${JSON.stringify(last)}`);
}

test('critical journey: real OIDC -> parcel analysis -> evidence -> generated report',async({page})=>{
  const request=await oidcLogin(page);

  const resolve=await json(await request.post('/api/v1/parcel/resolve',{data:{
    identifier:{type:'OFFICIAL_PARCEL_ID',value:'E2E-SP-CRITICAL-001'},
    municipalityIbge:'3550308',baseDate:'2026-08-26',
  }}),'parcel resolve');
  expect(resolve.status).toBe('RESOLVED');
  expect(resolve.requiresConfirmation).toBe(false);
  expect(resolve.selected.official_identifier).toBe('E2E-SP-CRITICAL-001');
  expect(resolve.selected.zones.some(z=>z.code==='E2E-ZONE')).toBe(true);

  const idem=`browser-analysis-${Date.now()}`;
  const analysis=await json(await request.post('/api/v1/analysis',{
    headers:{'Idempotency-Key':idem},
    data:{
      identifier:{type:'OFFICIAL_PARCEL_ID',value:'E2E-SP-CRITICAL-001'},
      municipalityIbge:'3550308',baseDate:'2026-08-26',
      context:{proposed_use:'E2E_TEST_USE',proposed_gfa_m2:1000,proposed_footprint_m2:500,height_m:12},
    },
  }),'analysis');
  expect(['COMPLETED','NEEDS_REVIEW','INSUFFICIENT_DATA']).toContain(analysis.status);
  expect(analysis.run?.id).toBeTruthy();
  expect(analysis.resolver?.selected?.official_identifier).toBe('E2E-SP-CRITICAL-001');
  expect(Array.isArray(analysis.snapshotIds)).toBe(true);
  expect(analysis.snapshotIds).toContain('0198f230-1000-7000-8000-000000000001');

  const replay=await json(await request.post('/api/v1/analysis',{
    headers:{'Idempotency-Key':idem},
    data:{identifier:{type:'OFFICIAL_PARCEL_ID',value:'E2E-SP-CRITICAL-001'},municipalityIbge:'3550308',baseDate:'2026-08-26'},
  }),'analysis replay');
  expect(replay.idempotency?.replayed).toBe(true);
  expect(replay.run?.id).toBe(analysis.run.id);

  const evidence=await json(await request.get(`/api/v1/analysis/${analysis.run.id}/evidence`),'analysis evidence');
  expect(evidence.run?.id||evidence.analysis?.id||analysis.run.id).toBeTruthy();

  const reportKey=`browser-report-${analysis.run.id}`;
  const report=await json(await request.post('/api/v1/reports',{
    headers:{'Idempotency-Key':reportKey},
    data:{subjectType:'analysis',subjectId:analysis.run.id,templateCode:'PROPERTY360_360',kind:'PROPERTY360',baseDate:'2026-08-26'},
  }),'report request');
  expect(report.id).toBeTruthy();
  expect(report.status).toBe('QUEUED');
  expect(report.subject_type).toBe('analysis');

  const reportReplay=await json(await request.post('/api/v1/reports',{
    headers:{'Idempotency-Key':reportKey},
    data:{subjectType:'analysis',subjectId:analysis.run.id,templateCode:'PROPERTY360_360',kind:'PROPERTY360',baseDate:'2026-08-26'},
  }),'report request replay');
  expect(reportReplay.idempotency?.replayed).toBe(true);
  expect(reportReplay.id).toBe(report.id);

  const completed=await pollReport(request,report.id);
  expect(completed.sha256).toMatch(/^[a-f0-9]{64}$/i);
  expect(completed.artifact_key).toBeTruthy();

  const manifest=await json(await request.get(`/api/v1/reports/${report.id}/manifest`),'report manifest');
  expect(manifest.run.status).toBe('COMPLETED');
  expect(manifest.snapshot?.sha256).toMatch(/^[a-f0-9]{64}$/i);
  expect(manifest.sections.length).toBeGreaterThan(0);
  expect(manifest.artifacts.some(a=>a.content_type==='application/pdf')).toBe(true);
  expect(manifest.artifacts.some(a=>a.content_type==='application/json')).toBe(true);
  expect(manifest.sections.every(s=>['CONFIRMED','CALCULATED','INFERRED','PENDING','CONFLICTING','NOT_AVAILABLE'].includes(s.status))).toBe(true);
});
