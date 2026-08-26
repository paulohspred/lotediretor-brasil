import {test,expect} from '@playwright/test';

const ADMIN='admin@lotediretor.local';
const PASSWORD='lotediretor';

async function login(page){
  await page.goto('/app/condominio',{waitUntil:'domcontentloaded'});
  await expect(page).toHaveURL(/\/login\?returnTo=/);
  await page.getByRole('link',{name:'Entrar com conta LoteDiretor'}).click();
  await page.locator('#username').fill(ADMIN);
  await page.locator('#password').fill(PASSWORD);
  await Promise.all([
    page.waitForURL(url=>url.pathname==='/app/condominio',{timeout:60_000}),
    page.locator('#kc-login').click(),
  ]);
}

async function readChat(page){
  const node=page.getByTestId('ai-chat-output-condominio');
  if(!(await node.count()))return null;
  try{return JSON.parse((await node.textContent())||'{}')}catch{return null}
}

test('critical UI journey: OIDC -> condomínio -> private upload -> indexed grounded chat',async({page})=>{
  await login(page);
  const nonce=Date.now();
  const marker=`AZULMAGNOLIA${nonce}`;

  await expect(page.getByRole('heading',{name:'Condomínio 360'})).toBeVisible();
  const nameInput=page.locator('input').first();
  await nameInput.fill(`Condomínio UI E2E ${nonce}`);
  await page.getByRole('button',{name:'Criar',exact:true}).first().click();

  const fileInput=page.locator('input[type="file"]');
  await expect(fileInput).toBeEnabled({timeout:30_000});
  const documentText=[
    'REGIMENTO INTERNO SINTÉTICO PARA TESTE AUTOMATIZADO.',
    `Marcador documental ${marker}.`,
    'Visitantes devem utilizar exclusivamente a vaga identificada como V-07 durante a permanência no condomínio.',
    'Este conteúdo é fixture privado de E2E e não constitui regra jurídica revisada.',
  ].join('\n');
  await fileInput.setInputFiles({name:`regimento-${nonce}.txt`,mimeType:'text/plain',buffer:Buffer.from(documentText,'utf8')});
  await expect(page.getByText(/Documento registrado\. OCR\/indexação/)).toBeVisible({timeout:30_000});

  const message=page.getByLabel('Mensagem A.I Condomínio');
  await expect(message).toBeVisible();
  await message.fill(`No documento ${marker}, qual orientação aparece para visitantes?`);
  const ask=page.getByTestId('ai-chat-condominio').getByRole('button',{name:'Consultar'});

  let chat=null;
  const deadline=Date.now()+75_000;
  while(Date.now()<deadline){
    await ask.click();
    await expect(page.getByTestId('ai-chat-output-condominio')).toBeVisible({timeout:15_000});
    chat=await readChat(page);
    const count=Number(chat?.retrieval?.lexicalCount||0)+Number(chat?.retrieval?.vectorCount||0);
    if(count>0)break;
    await page.waitForTimeout(1500);
  }

  expect(chat,'chat output after document indexing').toBeTruthy();
  expect(chat.assistant).toBe('condominio');
  expect(Number(chat.retrieval?.lexicalCount||0)+Number(chat.retrieval?.vectorCount||0)).toBeGreaterThan(0);
  expect(chat.retrieval?.errors||[]).toEqual([]);
  if(chat.status==='GROUNDED'){
    expect(Array.isArray(chat.evidence_ids)).toBe(true);
    expect(chat.evidence_ids.length).toBeGreaterThan(0);
    expect(String(chat.answer||'').length).toBeGreaterThan(0);
  }else{
    expect(chat.status).toBe('ABSTAINED');
    expect(chat.decision_status).toBe('NAO_DETERMINADO');
    expect(chat.limitations||[]).toContain('insufficient_grounding');
    expect(chat.evidence_ids||[]).toEqual([]);
  }
});
