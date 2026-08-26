import {test,expect} from '@playwright/test';

const ADMIN='admin@lotediretor.local';
const PASSWORD='lotediretor';

async function login(page){
  await page.goto('/app/ai-tec',{waitUntil:'domcontentloaded'});
  await expect(page).toHaveURL(/\/login\?returnTo=/);
  await page.getByRole('link',{name:'Entrar com conta LoteDiretor'}).click();
  await page.locator('#username').fill(ADMIN);
  await page.locator('#password').fill(PASSWORD);
  await Promise.all([
    page.waitForURL(url=>url.pathname==='/app/ai-tec',{timeout:60_000}),
    page.locator('#kc-login').click(),
  ]);
  return page.context().request;
}

async function json(response,label){
  const text=await response.text();
  let body;try{body=JSON.parse(text)}catch{throw new Error(`${label} returned non-JSON ${response.status()}: ${text.slice(0,1000)}`)}
  expect(response.ok(),`${label} ${response.status()}: ${text.slice(0,2000)}`).toBeTruthy();
  return body;
}

async function pollJob(request,id,timeoutMs=90_000){
  const deadline=Date.now()+timeoutMs;
  let last;
  while(Date.now()<deadline){
    last=await json(await request.get(`/api/v1/aitec/jobs/${id}`),'A.I TEC job status');
    if(last.status==='COMPLETED')return last;
    if(last.status==='FAILED'||last.status==='CANCELLED')throw new Error(`A.I TEC job terminal failure: ${JSON.stringify(last)}`);
    expect(['QUEUED','RUNNING']).toContain(last.status);
    await new Promise(resolve=>setTimeout(resolve,1000));
  }
  throw new Error(`A.I TEC job did not complete within ${timeoutMs}ms; last=${JSON.stringify(last)}`);
}

test('critical journey: real OIDC -> A.I TEC project -> queued v20 job -> worker -> reproducible persisted result',async({page})=>{
  const request=await login(page);
  const nonce=Date.now();

  const project=await json(await request.post('/api/v1/aitec/projects',{data:{name:`A.I TEC Browser Job ${nonce}`}}),'create A.I TEC project');
  expect(project.id).toBeTruthy();
  expect(project.status).toBe('DRAFT');

  const payload={
    operation:'terrain.tin',
    seed:42,
    kwargs:{samples:[
      {x:0,y:0,z:100},
      {x:10,y:0,z:101},
      {x:0,y:10,z:102},
      {x:10,y:10,z:103},
    ]},
  };

  const missingKey=await request.post(`/api/v1/aitec/projects/${project.id}/jobs`,{data:payload});
  expect(missingKey.status()).toBe(400);
  expect(await missingKey.text()).toContain('idempotency_key_required');

  const disallowed=await request.post(`/api/v1/aitec/projects/${project.id}/jobs`,{
    headers:{'Idempotency-Key':`browser-aitec-deny-${nonce}`},
    data:{operation:'shell.execute',kwargs:{command:'never-run'}},
  });
  expect(disallowed.status()).toBe(400);
  expect(await disallowed.text()).toContain('aitec_operation_not_allowed');

  const key=`browser-aitec-job-${nonce}`;
  const queued=await json(await request.post(`/api/v1/aitec/projects/${project.id}/jobs`,{
    headers:{'Idempotency-Key':key},data:payload,
  }),'queue A.I TEC job');

  expect(queued.id).toBeTruthy();
  expect(queued.project_id).toBe(project.id);
  expect(queued.operation).toBe('terrain.tin');
  expect(queued.status).toBe('QUEUED');
  expect(queued.attempts).toBe(0);
  expect(queued.execution_context.tenant_id).toBeTruthy();
  expect(queued.execution_context.project_id).toBe(project.id);
  expect(queued.execution_context.seed).toBe(42);

  const replay=await json(await request.post(`/api/v1/aitec/projects/${project.id}/jobs`,{
    headers:{'Idempotency-Key':key},data:payload,
  }),'replay A.I TEC job');
  expect(replay.idempotency.replayed).toBe(true);
  expect(replay.id).toBe(queued.id);

  const completed=await pollJob(request,queued.id);
  expect(completed.id).toBe(queued.id);
  expect(completed.project_id).toBe(project.id);
  expect(completed.operation).toBe('terrain.tin');
  expect(completed.status).toBe('COMPLETED');
  expect(completed.attempts).toBeGreaterThanOrEqual(1);
  expect(completed.solver_version).toBe('aitec-terrain-v20.1');
  expect(completed.classification).toBe('STUDY_PREPROJECT_NOT_EXECUTIVE');
  expect(completed.professional_review_required).toBe(true);
  expect(completed.engine_response.status).toBe('EXECUTED');
  expect(completed.engine_response.operation).toBe('terrain.tin');
  expect(completed.engine_response.context.project_id).toBe(project.id);
  expect(completed.engine_response.context.seed).toBe(42);
  expect(completed.engine_response.result.status).toBe('CALCULATED');
  expect(completed.engine_response.result.triangle_count).toBeGreaterThanOrEqual(2);
  expect(completed.completed_at).toBeTruthy();
});
