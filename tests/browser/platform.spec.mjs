import {test,expect,devices} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const USER='cliente@lotediretor.local';
const ADMIN='admin@lotediretor.local';
const PASSWORD='lotediretor';

async function assertNoBlockingA11y(page,label){
  const scan=await new AxeBuilder({page})
    .withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa'])
    .analyze();
  const blocking=scan.violations.filter(v=>v.impact==='serious'||v.impact==='critical');
  const compact=blocking.map(v=>({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.slice(0,5).map(n=>n.target)}));
  expect(blocking,`${label} has blocking accessibility violations: ${JSON.stringify(compact,null,2)}`).toEqual([]);
}

async function assertNoHorizontalOverflow(page,label){
  const overflow=await page.evaluate(()=>Math.max(0,document.documentElement.scrollWidth-window.innerWidth));
  expect(overflow,`${label} horizontally overflows the viewport`).toBeLessThanOrEqual(2);
}

async function oidcLogin(page,{returnTo='/app/dashboard',username=USER}={}){
  await page.goto(returnTo,{waitUntil:'domcontentloaded'});
  await expect(page).toHaveURL(/\/login\?returnTo=/);
  await expect(page.getByRole('heading',{name:'Acesse sua conta'})).toBeVisible();
  await page.getByRole('link',{name:'Entrar com conta LoteDiretor'}).click();
  await expect(page.locator('#username')).toBeVisible();
  await page.locator('#username').fill(username);
  await page.locator('#password').fill(PASSWORD);
  await Promise.all([
    page.waitForURL(url=>url.pathname===returnTo,{timeout:60_000}),
    page.locator('#kc-login').click(),
  ]);
  const session=(await page.context().cookies()).find(c=>c.name==='ld_session');
  expect(session,'OIDC callback must create ld_session').toBeTruthy();
  expect(session.httpOnly,'ld_session must remain HttpOnly').toBe(true);
}

function captureRuntimeFailures(page){
  const failures=[];
  page.on('pageerror',error=>failures.push(`pageerror:${error.message}`));
  page.on('response',response=>{
    if(response.status()>=500)failures.push(`http${response.status()}:${response.url()}`);
  });
  return failures;
}

test('public site and unauthenticated boundary are usable and accessible',async({page})=>{
  const failures=captureRuntimeFailures(page);
  const home=await page.goto('/',{waitUntil:'networkidle'});
  expect(home?.status()).toBeLessThan(500);
  await expect(page.getByRole('heading',{name:'Entenda o imóvel antes de decidir.'})).toBeVisible();
  await assertNoBlockingA11y(page,'public home');

  await page.goto('/app/dashboard',{waitUntil:'domcontentloaded'});
  await expect(page).toHaveURL(/\/login\?returnTo=/);
  await expect(page.getByRole('heading',{name:'Acesse sua conta'})).toBeVisible();
  await assertNoBlockingA11y(page,'login');
  expect(failures,failures.join('\n')).toEqual([]);
});

test('real OIDC user session reaches dashboard and every client workspace',async({page})=>{
  const failures=captureRuntimeFailures(page);
  await oidcLogin(page);
  await expect(page.getByRole('heading',{name:'Visão geral'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Módulos'})).toBeVisible();
  await assertNoBlockingA11y(page,'authenticated dashboard');

  const workspaces=[
    '/app/imovel-360',
    '/app/re-rural',
    '/app/condominio',
    '/app/energia-solar',
    '/app/ai-tec',
    '/app/prefeitura',
  ];
  for(const path of workspaces){
    const response=await page.goto(path,{waitUntil:'domcontentloaded'});
    expect(response?.status(),`${path} response`).toBeLessThan(500);
    await expect(page.locator('h1').first(),`${path} must expose a visible page heading`).toBeVisible();
  }
  expect(failures,failures.join('\n')).toEqual([]);
});

test('real OIDC admin session reaches Control Plane',async({page})=>{
  const failures=captureRuntimeFailures(page);
  await oidcLogin(page,{returnTo:'/admin/dashboard',username:ADMIN});
  await expect(page.getByRole('heading',{name:'Control Plane'})).toBeVisible();
  await expect(page.getByText('Negócio, governança, IA, dados e operação.')).toBeVisible();
  await assertNoBlockingA11y(page,'admin dashboard');
  expect(failures,failures.join('\n')).toEqual([]);
});

test('mobile authenticated dashboard fits viewport and preserves core navigation',async({browser})=>{
  const context=await browser.newContext({...devices['Pixel 5']});
  const page=await context.newPage();
  const failures=captureRuntimeFailures(page);
  try{
    await oidcLogin(page);
    await expect(page.getByRole('heading',{name:'Visão geral'})).toBeVisible();
    await assertNoHorizontalOverflow(page,'mobile dashboard');
    await assertNoBlockingA11y(page,'mobile dashboard');
    const aiTec=page.getByRole('link',{name:/A\.I TEC/}).first();
    await expect(aiTec).toBeVisible();
    await aiTec.click();
    await expect(page).toHaveURL(/\/app\/ai-tec/);
    await assertNoHorizontalOverflow(page,'mobile A.I TEC');
    expect(failures,failures.join('\n')).toEqual([]);
  }finally{
    await context.close();
  }
});
