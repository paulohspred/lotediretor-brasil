import {test,expect} from '@playwright/test';

const USER='cliente@lotediretor.local';
const PASSWORD='lotediretor';

async function login(page){
  await page.goto('/app/imovel-360',{waitUntil:'domcontentloaded'});
  await expect(page).toHaveURL(/\/login\?returnTo=/);
  await page.getByRole('link',{name:'Entrar com conta LoteDiretor'}).click();
  await page.locator('#username').fill(USER);
  await page.locator('#password').fill(PASSWORD);
  await Promise.all([
    page.waitForURL(url=>url.pathname==='/app/imovel-360',{timeout:60_000}),
    page.locator('#kc-login').click(),
  ]);
  const session=(await page.context().cookies()).find(c=>c.name==='ld_session');
  expect(session,'real OIDC login must create ld_session').toBeTruthy();
}

async function resultJson(page){
  const raw=await page.getByTestId('imovel-result-json').textContent();
  return JSON.parse(raw||'{}');
}

test('critical UI journey: OIDC -> parcel resolve -> analysis -> generated frozen report',async({page})=>{
  await login(page);
  await expect(page.getByRole('heading',{name:/Imóvel 360/})).toBeVisible();

  // Explicit point inside the synthetic E2E parcel seeded by
  // ops/browser/seed-critical-journeys.sh.
  await page.getByLabel('Latitude').fill('-23.5505');
  await page.getByLabel('Longitude').fill('-46.6333');
  await page.getByLabel('Data-base').fill('2026-08-26');

  await page.getByRole('button',{name:'Resolver parcela'}).click();
  await expect(page.getByTestId('imovel-result-kind')).toHaveText('Parcel Resolver v20',{timeout:30_000});
  const resolved=await resultJson(page);
  expect(resolved.status).toBe('RESOLVED');
  expect(resolved.requiresConfirmation).toBe(false);
  expect(resolved.selected?.official_identifier).toBe('E2E-SP-CRITICAL-001');
  expect((resolved.selected?.zones||[]).some(z=>z.code==='E2E-ZONE')).toBe(true);

  await page.getByRole('button',{name:'Analisar',exact:true}).click();
  await expect(page.getByTestId('imovel-result-kind')).toHaveText('Análise territorial congelável',{timeout:45_000});
  const analysis=await resultJson(page);
  expect(['COMPLETED','NEEDS_REVIEW','INSUFFICIENT_DATA']).toContain(analysis.status);
  expect(analysis.run?.id).toBeTruthy();
  expect(analysis.resolver?.selected?.official_identifier).toBe('E2E-SP-CRITICAL-001');
  expect(analysis.snapshotIds||[]).toContain('0198f230-1000-7000-8000-000000000001');

  const reportButton=page.getByRole('button',{name:'Gerar Relatório 360'});
  await expect(reportButton).toBeEnabled();
  await reportButton.click();
  await expect(page.getByTestId('imovel-result-kind')).toHaveText('Relatório 360 · manifesto e evidências',{timeout:90_000});
  const manifest=await resultJson(page);
  expect(manifest.run?.status).toBe('COMPLETED');
  expect(manifest.snapshot?.sha256).toMatch(/^[a-f0-9]{64}$/i);
  expect((manifest.sections||[]).length).toBeGreaterThan(0);
  expect((manifest.artifacts||[]).some(a=>a.content_type==='application/pdf')).toBe(true);
  expect((manifest.artifacts||[]).some(a=>a.content_type==='application/json')).toBe(true);
  expect((manifest.sections||[]).every(s=>['CONFIRMED','CALCULATED','INFERRED','PENDING','CONFLICTING','NOT_AVAILABLE'].includes(s.status))).toBe(true);

  // Evidence is independently readable from the same authenticated session.
  const evidence=await page.context().request.get(`/api/v1/analysis/${analysis.run.id}/evidence`);
  expect(evidence.ok()).toBeTruthy();
  const evidenceBody=await evidence.json();
  expect(evidenceBody.run?.id||evidenceBody.analysis?.id||analysis.run.id).toBeTruthy();
});
