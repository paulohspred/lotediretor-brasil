import {test,expect} from '@playwright/test';

const ADMIN='admin@lotediretor.local';
const PASSWORD='lotediretor';
const TENANT='0198f101-0000-7000-8000-000000000001';
const PAYMENT='0198f231-0000-7000-8000-000000000002';

async function login(page){
  await page.goto('/admin/billing',{waitUntil:'domcontentloaded'});
  await expect(page).toHaveURL(/\/login\?returnTo=/);
  await page.getByRole('link',{name:'Entrar com conta LoteDiretor'}).click();
  await page.locator('#username').fill(ADMIN);
  await page.locator('#password').fill(PASSWORD);
  await Promise.all([
    page.waitForURL(url=>url.pathname==='/admin/billing',{timeout:60_000}),
    page.locator('#kc-login').click(),
  ]);
}

test('critical UI journey: admin billing -> paid invoice -> synchronized entitlement',async({page})=>{
  await login(page);
  const nonce=Date.now();
  await expect(page.getByRole('heading',{name:'Billing / Entitlements'})).toBeVisible();

  await page.getByLabel('Tenant ID').fill(TENANT);
  await page.getByLabel('Payment ID').fill(PAYMENT);
  await page.getByLabel('Número da fatura').fill(`E2E-UI-ENTITLEMENT-${nonce}`);
  await page.getByLabel('Valor em centavos').fill('12345');

  const plan=page.getByLabel('Plano');
  await expect.poll(async()=>plan.inputValue(),{timeout:30_000}).not.toBe('');
  await expect(plan.locator('option:checked')).toContainText('foundation');

  await page.getByRole('button',{name:'Criar assinatura'}).click();
  await expect(page.getByTestId('billing-subscription-status')).toHaveText('ACTIVE',{timeout:30_000});

  await page.getByRole('button',{name:'Criar fatura'}).click();
  await expect(page.getByTestId('billing-invoice-status')).toHaveText('OPEN',{timeout:30_000});

  await page.getByRole('button',{name:'Alocar pagamento'}).click();
  await expect(page.getByTestId('billing-invoice-status')).toHaveText('PAID',{timeout:30_000});

  await page.getByRole('button',{name:'Aplicar entitlements'}).click();
  const resultNode=page.getByTestId('billing-entitlement-result');
  await expect(resultNode).toBeVisible({timeout:30_000});
  await expect(resultNode).toContainText('APPLIED_FROM_PAID_INVOICE');
  await expect(resultNode).toContainText('SYNCHRONIZED');
  await expect(resultNode).toContainText('foundation');

  const applied=JSON.parse((await resultNode.textContent())||'{}');
  expect(applied.status).toBe('APPLIED_FROM_PAID_INVOICE');
  expect(applied.platform?.status).toBe('SYNCHRONIZED');
  expect(applied.platform?.snapshot?.tier).toBe('foundation');
  expect(applied.platform?.snapshot?.modules||[]).toContain('imovel360');
  expect(applied.platform?.snapshot?.modules||[]).toContain('condominio');
  expect(applied.platform?.sessionsUpdated).toBeGreaterThan(0);

  const me=await page.context().request.get('/api/v1/auth/me');
  expect(me.ok()).toBeTruthy();
  const session=await me.json();
  expect(session.entitlements?.tier).toBe('foundation');
  expect(session.entitlements?.billing?.invoiceId).toBe(applied.platform.snapshot.billing.invoiceId);
});
