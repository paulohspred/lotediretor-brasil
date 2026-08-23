from __future__ import annotations
import os,time,uuid,requests,psycopg
from psycopg.types.json import Jsonb
CONTROL=os.environ['CONTROL_DATABASE_URL']; PLATFORM=os.environ['PLATFORM_DATABASE_URL']; TOKEN=os.getenv('MERCADO_PAGO_ACCESS_TOKEN','')
def valid_uuid(v):
 try:return str(uuid.UUID(str(v)))
 except:return None
def process_one():
 with psycopg.connect(CONTROL) as c:
  with c.transaction():
   row=c.execute("select id,resource_id,topic,payload from billing.webhook_event where provider='MERCADO_PAGO' and verified=true and processed_at is null and (processing_at is null or processing_at < now()-interval '10 minutes') order by received_at for update skip locked limit 1").fetchone()
   if not row:return False
   eid,rid,topic,payload=row
   c.execute("update billing.webhook_event set processing_at=now(),error=null where id=%s",(eid,))
  try:
   if topic!='payment': raise ValueError(f'unsupported_topic:{topic}')
   if not TOKEN: raise ValueError('MERCADO_PAGO_ACCESS_TOKEN_not_configured')
   resp=requests.get(f'https://api.mercadopago.com/v1/payments/{rid}',headers={'Authorization':f'Bearer {TOKEN}'},timeout=30);resp.raise_for_status();p=resp.json()
   tenant_id=valid_uuid(p.get('external_reference')) or valid_uuid((p.get('metadata') or {}).get('tenant_id'))
   if not tenant_id: raise ValueError('tenant_reference_missing')
   tenant=c.execute('select id,platform_organization_id from tenant.tenant where id=%s',(tenant_id,)).fetchone()
   if not tenant: raise ValueError('tenant_not_found')
   amount=int(round(float(p.get('transaction_amount') or 0)*100));fee=int(round(sum(float(x.get('amount') or 0) for x in (p.get('fee_details') or []))*100));net=amount-fee;status=str(p.get('status') or 'unknown').upper()
   with c.transaction():
    pay=c.execute("insert into billing.payment(tenant_id,provider,provider_payment_id,amount_cents,currency,status,gross_cents,fee_cents,net_cents) values(%s,'MERCADO_PAGO',%s,%s,%s,%s,%s,%s,%s) on conflict(provider,provider_payment_id) do update set status=excluded.status,gross_cents=excluded.gross_cents,fee_cents=excluded.fee_cents,net_cents=excluded.net_cents returning id",(tenant_id,str(p.get('id')),amount,str(p.get('currency_id') or 'BRL')[:3],status,amount,fee,net)).fetchone()[0]
    if status in ('APPROVED','PAID'):
      c.execute("insert into billing.ledger_entry(tenant_id,kind,amount_cents,currency,reference_type,reference_id) values(%s,'PAYMENT',%s,%s,'billing.payment',%s) on conflict do nothing",(tenant_id,net,str(p.get('currency_id') or 'BRL')[:3],pay))
    c.execute("update billing.webhook_event set processed_at=now(),processing_at=null,error=null where id=%s",(eid,))
   org=tenant[1]
   if org and status in ('APPROVED','PAID'):
    sub=c.execute("select pv.entitlements from billing.subscription s join catalog.plan_version pv on pv.id=s.plan_version_id where s.tenant_id=%s order by s.created_at desc limit 1",(tenant_id,)).fetchone()
    if sub:
      with psycopg.connect(PLATFORM) as pc: pc.execute("insert into core.entitlement_snapshot(organization_id,snapshot,valid_from) values(%s,%s,now())",(org,Jsonb(sub[0])));pc.commit()
  except Exception as e:
   with c.transaction():c.execute("update billing.webhook_event set error=%s,processing_at=null where id=%s",(str(e)[:1200],eid))
   print('billing event failed',eid,e,flush=True);time.sleep(5)
 return True
while True:
 try:
  if not process_one():time.sleep(3)
 except Exception as e:print('billing loop error',e,flush=True);time.sleep(5)
