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
  const session=(await page.context().cookies()).find(c=>c.name==='ld_session');
  expect(session,'real OIDC login must create ld_session').toBeTruthy();
}

test('critical UI journey: OIDC -> A.I TEC project -> persisted v20 job -> worker -> auditable result',async({page})=>{
  await login(page);
  const nonce=Date.now();

  await expect(page.getByRole('heading',{name:'A.I TEC'})).toBeVisible();
  await page.getByLabel('Nome do projeto').fill(`A.I TEC UI Job ${nonce}`);
  await page.getByRole('button',{name:'Criar',exact:true}).click();

  const runButton=page.getByRole('button',{name:'Executar job v20'});
  await expect(runButton).toBeEnabled({timeout:30_000});
  await page.getByLabel('Amostras TIN JSON').fill(JSON.stringify([
    {x:0,y:0,z:100},
    {x:10,y:0,z:101},
    {x:0,y:10,z:102},
    {x:10,y:10,z:103},
  ]));
  await page.getByLabel('Seed do job').fill('42');
  await runButton.click();

  const status=page.getByTestId('aitec-job-status');
  await expect(status).toContainText('COMPLETED',{timeout:90_000});
  const resultNode=page.getByTestId('aitec-job-result');
  await expect(resultNode).toContainText('aitec-terrain-v20.1');
  await expect(resultNode).toContainText('STUDY_PREPROJECT_NOT_EXECUTIVE');
  await expect(resultNode).toContainText('professional_review_required');
  await expect(resultNode).toContainText('true');
  await expect(resultNode).toContainText('triangle_count');

  const raw=await resultNode.textContent();
  const completed=JSON.parse(raw||'{}');
  expect(completed.status).toBe('COMPLETED');
  expect(completed.operation).toBe('terrain.tin');
  expect(completed.attempts).toBeGreaterThanOrEqual(1);
  expect(completed.engine_response?.context?.project_id).toBe(completed.project_id);
  expect(completed.engine_response?.context?.seed).toBe(42);
  expect(completed.engine_response?.result?.status).toBe('CALCULATED');
  expect(completed.engine_response?.result?.triangle_count).toBeGreaterThanOrEqual(2);

  // Boundary assertions stay in the same authenticated browser session while
  // the primary business journey above is driven through visible UI controls.
  const request=page.context().request;
  const payload={operation:'terrain.tin',seed:42,kwargs:{samples:[{x:0,y:0,z:1},{x:1,y:0,z:2},{x:0,y:1,z:3}]}};
  const missingKey=await request.post(`/api/v1/aitec/projects/${completed.project_id}/jobs`,{data:payload});
  expect(missingKey.status()).toBe(400);
  expect(await missingKey.text()).toContain('idempotency_key_required');

  const disallowed=await request.post(`/api/v1/aitec/projects/${completed.project_id}/jobs`,{
    headers:{'Idempotency-Key':`browser-aitec-deny-${nonce}`},
    data:{operation:'shell.execute',kwargs:{command:'never-run'}},
  });
  expect(disallowed.status()).toBe(400);
  expect(await disallowed.text()).toContain('aitec_operation_not_allowed');
});
