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

test('critical journey: real OIDC -> A.I TEC project -> persisted v20 job -> reproducible result',async({page})=>{
  const request=await login(page);
  const nonce=Date.now();

  const project=await json(await request.post('/api/v1/aitec/projects',{data:{name:`A.I TEC Browser Job ${nonce}`}}),'create A.I TEC project');
  expect(project.id).toBeTruthy();
  expect(project.status).toBe('DRAFT');

  const key=`browser-aitec-job-${nonce}`;
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
  const job=await json(await request.post(`/api/v1/aitec/projects/${project.id}/jobs`,{
    headers:{'Idempotency-Key':key},data:payload,
  }),'create A.I TEC job');

  expect(job.id).toBeTruthy();
  expect(job.project_id).toBe(project.id);
  expect(job.status).toBe('COMPLETED');
  expect(job.solver_version).toBe('aitec-terrain-v20.1');
  expect(job.metrics.operation).toBe('terrain.tin');
  expect(job.metrics.seed).toBe(42);
  expect(job.metrics.classification).toBe('STUDY_PREPROJECT_NOT_EXECUTIVE');
  expect(job.metrics.professional_review_required).toBe(true);
  expect(job.metrics.result.status).toBe('CALCULATED');
  expect(job.metrics.result.triangle_count).toBeGreaterThanOrEqual(2);

  const replay=await json(await request.post(`/api/v1/aitec/projects/${project.id}/jobs`,{
    headers:{'Idempotency-Key':key},data:payload,
  }),'replay A.I TEC job');
  expect(replay.idempotency.replayed).toBe(true);
  expect(replay.id).toBe(job.id);

  const persisted=await json(await request.get(`/api/v1/aitec/jobs/${job.id}`),'get A.I TEC job');
  expect(persisted.id).toBe(job.id);
  expect(persisted.project_id).toBe(project.id);
  expect(persisted.status).toBe('COMPLETED');
  expect(persisted.solver_version).toBe('aitec-terrain-v20.1');
  expect(persisted.metrics.result.triangle_count).toBe(job.metrics.result.triangle_count);
});
