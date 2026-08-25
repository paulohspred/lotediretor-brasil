import {createHash} from 'crypto';

export const ADMIN_SAAS_V20_VERSION='admin-saas-v20.1';
export const SUPPORT_SCOPES=new Set(['READ_DATA','VIEW_CONFIG','BILLING_SUPPORT','IMPERSONATE_USER']);

export function stableHash(value:any){return createHash('sha256').update(typeof value==='string'?value:JSON.stringify(value)).digest('hex');}
export function money(value:any,name='amountCents'){const n=Number(value);if(!Number.isSafeInteger(n)||n<0)throw new Error(`${name}_must_be_non_negative_integer`);return n;}

export function dunningPolicy(attempt:any,now=new Date()){
  const n=Number(attempt);if(!Number.isInteger(n)||n<0)throw new Error('attempt_invalid');
  const delays=[1,3,7,14];
  if(n>=delays.length)return{status:'EXHAUSTED',attempt:n,nextAttemptAt:null};
  const next=new Date(now.getTime()+delays[n]*86400000);
  return{status:'RETRY_SCHEDULED',attempt:n+1,nextAttemptAt:next.toISOString(),delayDays:delays[n]};
}

export function refundGuard(input:any){
  const status=String(input?.paymentStatus||'').toUpperCase();if(!['APPROVED','PAID'].includes(status))return{status:'BLOCKED',reason:'payment_not_settled'};
  const paid=money(input?.paymentAmountCents,'paymentAmountCents'),requested=money(input?.requestedCents,'requestedCents');
  const already=money(input?.alreadyAdjustedCents||0,'alreadyAdjustedCents');
  if(requested<=0)return{status:'BLOCKED',reason:'positive_refund_required'};
  if(already+requested>paid)return{status:'BLOCKED',reason:'refund_exceeds_settled_amount',remainingCents:Math.max(0,paid-already)};
  return{status:'READY',amountCents:requested,remainingAfterCents:paid-already-requested};
}

export function chargebackGuard(input:any){
  const status=String(input?.paymentStatus||'').toUpperCase();if(!['APPROVED','PAID'].includes(status))return{status:'BLOCKED',reason:'payment_not_settled'};
  const paid=money(input?.paymentAmountCents,'paymentAmountCents'),already=money(input?.alreadyAdjustedCents||0,'alreadyAdjustedCents');
  const amount=input?.requestedCents==null?paid-already:money(input.requestedCents,'requestedCents');
  if(amount<=0||already+amount>paid)return{status:'BLOCKED',reason:'chargeback_amount_invalid',remainingCents:Math.max(0,paid-already)};
  return{status:'READY',amountCents:amount,remainingAfterCents:paid-already-amount};
}

export function invoiceTotals(lines:any[],coupon:any=null){
  const normalized=(Array.isArray(lines)?lines:[]).map((line:any)=>{const quantity=Number(line?.quantity??1);if(!Number.isFinite(quantity)||quantity<0)throw new Error('invoice_quantity_invalid');const unit=Number(line?.unitCents);if(!Number.isSafeInteger(unit))throw new Error('invoice_unit_cents_invalid');return{...line,quantity,unitCents:unit,amountCents:Math.round(quantity*unit)};});
  const subtotal=normalized.reduce((s:number,x:any)=>s+x.amountCents,0);if(subtotal<0)throw new Error('invoice_subtotal_negative');
  let discount=0;if(coupon){const kind=String(coupon.kind||'').toUpperCase(),value=Number(coupon.value||0);if(kind==='PERCENT')discount=Math.round(subtotal*Math.min(100,Math.max(0,value))/100);else if(kind==='FIXED')discount=Math.min(subtotal,Math.round(value));}
  return{lines:normalized,subtotalCents:subtotal,discountCents:discount,totalCents:Math.max(0,subtotal-discount)};
}

export function supportSessionGate(input:any){
  const requester=String(input?.requestedBy||''),approver=String(input?.approvedBy||'');
  if(!requester||!approver)return{status:'BLOCKED',reason:'requester_and_approver_required'};
  if(requester===approver)return{status:'BLOCKED',reason:'maker_checker_violation'};
  const scopes=[...new Set((Array.isArray(input?.scopes)?input.scopes:[]).map((x:any)=>String(x).toUpperCase()))];
  const invalid=scopes.filter(x=>!SUPPORT_SCOPES.has(x));if(invalid.length)return{status:'BLOCKED',reason:'invalid_scope',invalid};
  if(!scopes.length)return{status:'BLOCKED',reason:'scope_required'};
  const now=new Date(input?.now||Date.now()),expires=new Date(input?.expiresAt);if(Number.isNaN(expires.getTime())||expires<=now)return{status:'BLOCKED',reason:'expiry_invalid'};
  const ttlMinutes=Math.round((expires.getTime()-now.getTime())/60000);if(ttlMinutes>240)return{status:'BLOCKED',reason:'support_session_ttl_exceeds_4h'};
  if(scopes.includes('IMPERSONATE_USER')&&!String(input?.targetSubject||'').trim())return{status:'BLOCKED',reason:'target_subject_required_for_impersonation'};
  if(!String(input?.reason||'').trim())return{status:'BLOCKED',reason:'reason_required'};
  return{status:'READY',scopes,ttlMinutes};
}

function bucket(seed:string){return parseInt(stableHash(seed).slice(0,12),16)%10000/100;}
export function experimentAssignment(input:any){
  const variants=Array.isArray(input?.variants)?input.variants.map(String).filter(Boolean):[];if(!variants.length)throw new Error('variants_required');
  const b=bucket(`${input?.tenantId}:${input?.experimentId}:${input?.subjectHash}`);const allocation=Math.min(100,Math.max(0,Number(input?.allocationPercent??100)));
  if(b>=allocation)return{assigned:false,bucket:b,variant:null};
  const slice=allocation/variants.length;const index=Math.min(variants.length-1,Math.floor(b/Math.max(slice,0.000001)));
  return{assigned:true,bucket:b,variant:variants[index]};
}

export function featureRollout(input:any){
  if(input?.enabled!==true)return{enabled:false,variant:null,bucket:null};
  const percent=Math.min(100,Math.max(0,Number(input?.rolloutPercent??100)));const b=bucket(`${input?.tenantId}:${input?.flagCode}`);
  return{enabled:b<percent,variant:b<percent?(input?.variant||null):null,bucket:b,rolloutPercent:percent};
}

export function aiCostMicros(input:any){
  const it=money(input?.inputTokens||0,'inputTokens'),ot=money(input?.outputTokens||0,'outputTokens');
  const ir=money(input?.inputRateMicrosPerMillion||0,'inputRateMicrosPerMillion'),or=money(input?.outputRateMicrosPerMillion||0,'outputRateMicrosPerMillion');
  return Math.round((it*ir+ot*or)/1_000_000);
}

export function reconciliation(input:any){
  const paymentNet=Number(input?.paymentNetCents||0),adjustments=Number(input?.adjustmentCents||0),ledger=Number(input?.ledgerCents||0);
  for(const [k,v] of Object.entries({paymentNet,adjustments,ledger}))if(!Number.isSafeInteger(v))throw new Error(`${k}_invalid`);
  const expected=paymentNet-adjustments,difference=ledger-expected;
  return{status:difference===0?'BALANCED':'DIFFERENCE',paymentNetCents:paymentNet,adjustmentCents:adjustments,expectedLedgerCents:expected,ledgerCents:ledger,differenceCents:difference};
}

export function nfseGuard(input:any){
  if(input?.applicable===false)return{status:'NOT_APPLICABLE'};
  const missing:string[]=[];if(!input?.tenantId)missing.push('tenantId');if(!input?.invoiceId)missing.push('invoiceId');if(!String(input?.requestedBy||'').trim())missing.push('requestedBy');
  return missing.length?{status:'BLOCKED',missing}:{status:'REQUESTED',policy:'Fiscal provider authorization remains an external execution gate; store request and provider evidence only.'};
}
