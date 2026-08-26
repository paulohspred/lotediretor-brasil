import {test,expect} from '@playwright/test';

const USER='cliente@lotediretor.local';
const ADMIN='admin@lotediretor.local';
const PASSWORD='lotediretor';
const LOCAL_CONTROL_TENANT='0198f101-0000-7000-8000-000000000001';
const BILLING_PAYMENT_FIXTURE='0198f231-0000-7000-8000-000000000001';

test.describe.configure({mode:'serial'});

async function oidcLogin(page,{returnTo='/app/dashboard',user=USER}={}){
  await page.goto(returnTo,{waitUntil:'domcontentloaded'});
  await expect(page).toHaveURL(/\/login\?returnTo=/);
  await page.getByRole('link',{name:'Entrar com conta LoteDiretor'}).click();
  await page.locator('#username').fill(user);
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

test('critical journey: billing settlement -> paid invoice -> platform entitlement snapshot',async({page})=>{
  const request=await oidcLogin(page,{returnTo:'/admin/dashboard',user:ADMIN});

  const plans=await json(await request.get('/control/v1/catalog/plans'),'plans');
  const foundation=plans.items.find(p=>p.code==='foundation'&&p.status==='ACTIVE');
  expect(foundation,'active foundation plan fixture').toBeTruthy();

  const subscription=await json(await request.post('/control/v20/billing/subscriptions',{
    headers:{'Idempotency-Key':'browser-billing-subscription-v20'},
    data:{tenantId:LOCAL_CONTROL_TENANT,planVersionId:foundation.id,status:'ACTIVE',provider:'E2E_FIXTURE',providerSubscriptionId:'browser-subscription-001',reason:'critical browser journey'},
  }),'subscription');
  expect(subscription.id).toBeTruthy();
  expect(subscription.status).toBe('ACTIVE');

  const invoice=await json(await request.post('/control/v20/billing/invoices',{
    headers:{'Idempotency-Key':'browser-billing-invoice-v20'},
    data:{
      tenantId:LOCAL_CONTROL_TENANT,subscriptionId:subscription.id,invoiceNumber:'E2E-BROWSER-ENTITLEMENT-001',
      lines:[{lineType:'PLAN',description:'Foundation E2E entitlement proof',quantity:1,unitCents:12345}],
      metadata:{synthetic:true,purpose:'billing_to_entitlement_browser_e2e'},reason:'critical browser journey',
    },
  }),'invoice');
  expect(invoice.id).toBeTruthy();
  expect(invoice.status).toBe('OPEN');
  expect(Number(invoice.total_cents)).toBe(12345);

  const allocation=await json(await request.post(`/control/v20/billing/payments/${BILLING_PAYMENT_FIXTURE}/allocate`,{
    headers:{'Idempotency-Key':'browser-billing-allocation-v20'},
    data:{tenantId:LOCAL_CONTROL_TENANT,invoiceId:invoice.id,amountCents:12345,reason:'synthetic settled payment allocation'},
  }),'payment allocation');
  expect(allocation.invoice.status).toBe('PAID');
  expect(Number(allocation.invoice.paid_cents)).toBe(12345);

  const applied=await json(await request.post(`/control/v20/billing/invoices/${invoice.id}/apply-entitlements`),'apply entitlements');
  expect(applied.status).toBe('APPLIED_FROM_PAID_INVOICE');
  expect(applied.platform.status).toBe('SYNCHRONIZED');
  expect(applied.platform.snapshot.tier).toBe('foundation');
  expect(applied.platform.snapshot.billing.invoiceId).toBe(invoice.id);
  expect(applied.platform.snapshot.billing.subscriptionId).toBe(subscription.id);
  expect(applied.platform.snapshot.modules).toContain('imovel360');
  expect(applied.platform.snapshot.modules).toContain('condominio');
  expect(applied.platform.sessionsUpdated).toBeGreaterThan(0);

  const me=await json(await request.get('/api/v1/auth/me'),'auth me after entitlement sync');
  expect(me.entitlements.billing.invoiceId).toBe(invoice.id);
  expect(me.entitlements.tier).toBe('foundation');
});
