from pathlib import Path

root=Path(__file__).resolve().parents[1]

def text(path:str): return (root/path).read_text(encoding='utf-8')

imovel=text('apps/client-web/components/workspaces/Imovel360Workspace.tsx')
aitec=text('apps/client-web/components/workspaces/AitecWorkspace.tsx')
api_box=text('apps/client-web/components/workspaces/ApiBox.tsx')
chat=text('apps/client-web/components/workspaces/AiChatBox.tsx')
billing=text('apps/admin-web/components/BillingWorkspace.tsx')
billing_page=text('apps/admin-web/app/billing/page.tsx')
config=text('tests/browser/playwright.config.mjs')

for needle in [
    "templateCode:'PROPERTY360_360'",
    "pollJson(`/api/v1/reports/${queued.id}/status`",
    'imovel-result-kind','imovel-result-json',
]: assert needle in imovel, f'Imovel 360 UI missing critical report contract: {needle}'

for needle in [
    "operation:'terrain.tin'",
    "postJson(`/api/v1/aitec/projects/${selected}/jobs`",
    'waitForJob(queued.id,12*60*1000)',
    "getJson(`/api/v1/aitec/jobs/${queued.id}`",
    'aitec-job-status','aitec-job-result','professional',
]: assert needle in aitec, f'A.I TEC UI missing persisted job contract: {needle}'
for needle in [
    'export async function waitForJob',
    'new EventSource(',
    '/events',
]: assert needle in api_box, f'ApiBox missing durable SSE job stream contract: {needle}'

for needle in ['ai-chat-output-${assistant}','credentials:\'include\'','subjectId','baseDate']:
    assert needle in chat, f'grounded chat UI missing contract: {needle}'

for needle in [
    '/control/v20/billing/subscriptions',
    '/control/v20/billing/invoices',
    '/allocate',
    '/apply-entitlements',
    'billing-subscription-status','billing-invoice-status','billing-entitlement-result',
]: assert needle in billing, f'Admin billing UI missing entitlement journey contract: {needle}'
assert 'BillingWorkspace' in billing_page

specs=['imovel-ui.spec.mjs','condo-ui.spec.mjs','billing-ui.spec.mjs','aitec-job.spec.mjs']
for spec in specs:
    assert (root/'tests/browser'/spec).exists(), f'missing critical UI spec: {spec}'
    pattern=spec.replace('.',r'\\.')
    assert spec.split('.')[0].replace('-','-') in config or pattern in config, f'Playwright config does not include {spec}'

# Primary browser specs must visibly drive the UI rather than only using
# page.context().request for their success path.
assert "getByRole('button',{name:'Gerar Relatório 360'}" in text('tests/browser/imovel-ui.spec.mjs')
assert "getByTestId('ai-chat-condominio')" in text('tests/browser/condo-ui.spec.mjs')
assert "getByRole('button',{name:'Aplicar entitlements'}" in text('tests/browser/billing-ui.spec.mjs')
assert "getByRole('button',{name:'Executar job v20'}" in text('tests/browser/aitec-job.spec.mjs')

print('v20 critical UI journeys contract OK')
