'use client';
import {useEffect,useMemo,useState} from 'react';
import {Badge,Card} from '@lotediretor/ui';

async function json(url:string,init?:RequestInit){
  const r=await fetch(url,{credentials:'include',cache:'no-store',...init});
  const x=await r.json().catch(()=>null);
  if(!r.ok)throw new Error(x?.message||x?.code||`HTTP ${r.status}`);
  return x;
}
async function post(url:string,body?:any,idempotent=false){
  const headers:Record<string,string>={};
  if(body!==undefined)headers['content-type']='application/json';
  if(idempotent)headers['Idempotency-Key']=globalThis.crypto?.randomUUID?.()||`${Date.now()}-${Math.random()}`;
  return json(url,{method:'POST',headers,body:body===undefined?undefined:JSON.stringify(body)});
}

export function BillingWorkspace(){
  const [plans,setPlans]=useState<any[]>([]);const [summary,setSummary]=useState<any>(null);const [error,setError]=useState('');const [busy,setBusy]=useState('');
  const [tenantId,setTenantId]=useState('');const [planId,setPlanId]=useState('');const [paymentId,setPaymentId]=useState('');const [invoiceNumber,setInvoiceNumber]=useState(`ADMIN-${Date.now()}`);const [amount,setAmount]=useState('12345');
  const [subscription,setSubscription]=useState<any>(null);const [invoice,setInvoice]=useState<any>(null);const [allocation,setAllocation]=useState<any>(null);const [entitlement,setEntitlement]=useState<any>(null);
  const activePlans=useMemo(()=>plans.filter(x=>x.status==='ACTIVE'),[plans]);
  async function refresh(){const [p,s]=await Promise.all([json('/control/v1/catalog/plans'),json('/control/v1/billing/summary')]);setPlans(p.items||[]);setSummary(s);if(!planId){const foundation=(p.items||[]).find((x:any)=>x.code==='foundation'&&x.status==='ACTIVE')||(p.items||[]).find((x:any)=>x.status==='ACTIVE');if(foundation)setPlanId(foundation.id)}}
  useEffect(()=>{refresh().catch(e=>setError(e.message))},[]);
  async function run(name:string,fn:()=>Promise<void>){setBusy(name);setError('');try{await fn();await refresh()}catch(e:any){setError(e?.message||String(e))}finally{setBusy('')}}
  async function createSubscription(){await run('subscription',async()=>{if(!tenantId||!planId)throw new Error('Tenant e plano são obrigatórios.');const x=await post('/control/v20/billing/subscriptions',{tenantId,planVersionId:planId,status:'ACTIVE',provider:'ADMIN_UI',providerSubscriptionId:`admin-ui-${Date.now()}`,reason:'admin billing workspace'},true);setSubscription(x)})}
  async function createInvoice(){await run('invoice',async()=>{if(!tenantId||!subscription?.id)throw new Error('Crie a assinatura antes da fatura.');const cents=Number(amount);if(!Number.isInteger(cents)||cents<=0)throw new Error('Valor em centavos inválido.');const x=await post('/control/v20/billing/invoices',{tenantId,subscriptionId:subscription.id,invoiceNumber,lines:[{lineType:'PLAN',description:'Plano via Admin Billing',quantity:1,unitCents:cents}],metadata:{origin:'admin_billing_workspace'},reason:'admin billing workspace'},true);setInvoice(x)})}
  async function allocate(){await run('allocation',async()=>{if(!tenantId||!invoice?.id||!paymentId)throw new Error('Tenant, fatura e pagamento são obrigatórios.');const x=await post(`/control/v20/billing/payments/${encodeURIComponent(paymentId)}/allocate`,{tenantId,invoiceId:invoice.id,amountCents:Number(amount),reason:'admin billing workspace settlement'},true);setAllocation(x);if(x?.invoice)setInvoice(x.invoice)})}
  async function applyEntitlements(){await run('entitlement',async()=>{if(!invoice?.id)throw new Error('Fatura obrigatória.');const x=await post(`/control/v20/billing/invoices/${encodeURIComponent(invoice.id)}/apply-entitlements`);setEntitlement(x)})}

  return <>
    <header className="ahead"><div><h1>Billing / Entitlements</h1><div className="sub">Assinatura, faturamento, liquidação e sincronização auditável de entitlements.</div></div><Badge tone="success">v20 · operational</Badge></header>
    {error&&<Card className="atable"><div className="adminError" role="alert">{error}</div></Card>}
    <Card className="atable" data-testid="billing-workspace">
      <h3>Contexto</h3>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(220px,1fr))',gap:12}}>
        <label>Tenant ID<input aria-label="Tenant ID" value={tenantId} onChange={e=>setTenantId(e.target.value)} placeholder="UUID do tenant"/></label>
        <label>Plano<select aria-label="Plano" value={planId} onChange={e=>setPlanId(e.target.value)}><option value="">Selecione</option>{activePlans.map((p:any)=><option value={p.id} key={p.id}>{p.code} · v{p.version}</option>)}</select></label>
        <label>Payment ID<input aria-label="Payment ID" value={paymentId} onChange={e=>setPaymentId(e.target.value)} placeholder="Pagamento liquidado"/></label>
        <label>Número da fatura<input aria-label="Número da fatura" value={invoiceNumber} onChange={e=>setInvoiceNumber(e.target.value)}/></label>
        <label>Valor (centavos)<input aria-label="Valor em centavos" value={amount} onChange={e=>setAmount(e.target.value)}/></label>
      </div>
      <div style={{display:'flex',gap:8,flexWrap:'wrap',marginTop:14}}>
        <button disabled={!!busy||!tenantId||!planId} onClick={()=>void createSubscription()}>{busy==='subscription'?'Criando…':'Criar assinatura'}</button>
        <button disabled={!!busy||!subscription?.id} onClick={()=>void createInvoice()}>{busy==='invoice'?'Criando…':'Criar fatura'}</button>
        <button disabled={!!busy||!invoice?.id||!paymentId} onClick={()=>void allocate()}>{busy==='allocation'?'Alocando…':'Alocar pagamento'}</button>
        <button disabled={!!busy||invoice?.status!=='PAID'} onClick={()=>void applyEntitlements()}>{busy==='entitlement'?'Sincronizando…':'Aplicar entitlements'}</button>
      </div>
    </Card>
    <div className="akpis second">
      <Card className="akpi"><small>Assinatura</small><b data-testid="billing-subscription-status">{subscription?.status||'—'}</b></Card>
      <Card className="akpi"><small>Fatura</small><b data-testid="billing-invoice-status">{invoice?.status||'—'}</b></Card>
    </div>
    {entitlement&&<Card className="atable"><h3>Entitlement sincronizado</h3><pre data-testid="billing-entitlement-result">{JSON.stringify(entitlement,null,2)}</pre></Card>}
    {allocation&&<Card className="atable"><h3>Liquidação</h3><pre>{JSON.stringify(allocation,null,2)}</pre></Card>}
    <Card className="atable"><h3>Resumo</h3><pre>{JSON.stringify(summary,null,2)}</pre></Card>
  </>;
}
