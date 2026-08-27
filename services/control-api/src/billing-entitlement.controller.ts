import {Controller,HttpException,Param,Post,Req} from '@nestjs/common';
import {Pool,PoolClient} from 'pg';
import Redis from 'ioredis';

const pool=new Pool({connectionString:process.env.CONTROL_DATABASE_URL});
const redis=new Redis(process.env.VALKEY_URL||'redis://localhost:6379/0');

async function requireAdmin(req:any){
  const sid=req.cookies?.ld_session;if(!sid)throw new HttpException('unauthorized',401);
  const raw=await redis.get(`session:${sid}`);if(!raw)throw new HttpException('unauthorized',401);
  const session=JSON.parse(raw);if(!session.roles?.includes('admin'))throw new HttpException('forbidden',403);return session;
}
async function adminTx<T>(fn:(c:PoolClient)=>Promise<T>){
  const c=await pool.connect();try{await c.query('BEGIN');await c.query(`select set_config('app.control_admin','true',true)`);const out=await fn(c);await c.query('COMMIT');return out;}catch(e){await c.query('ROLLBACK');throw e;}finally{c.release();}
}
function object(value:any){return value&&typeof value==='object'&&!Array.isArray(value)?value:{};}
function strings(value:any){return (Array.isArray(value)?value:[]).map((x:any)=>String(x).trim()).filter(Boolean);}

@Controller('control/v20/billing')
export class BillingEntitlementController{
  @Post('invoices/:invoiceId/apply-entitlements')
  async apply(@Req() req:any,@Param('invoiceId') invoiceId:string){
    const actor=await requireAdmin(req);
    const prepared=await adminTx(async c=>{
      const r=await c.query(`select i.id,i.invoice_number,i.status invoice_status,i.tenant_id,i.subscription_id,t.status tenant_status,t.platform_organization_id,
        s.status subscription_status,p.code plan_code,p.status plan_status,p.entitlements plan_entitlements
        from billing.invoice i join tenant.tenant t on t.id=i.tenant_id join billing.subscription s on s.id=i.subscription_id join catalog.plan_version p on p.id=s.plan_version_id
        where i.id=$1 for update`,[invoiceId]);
      if(!r.rowCount)throw new HttpException('invoice_with_subscription_not_found',404);
      const row=r.rows[0];
      if(row.invoice_status!=='PAID')throw new HttpException('paid_invoice_required',409);
      if(row.tenant_status!=='ACTIVE'||!row.platform_organization_id)throw new HttpException('active_platform_mapped_tenant_required',409);
      if(!['ACTIVE','TRIALING'].includes(String(row.subscription_status).toUpperCase()))throw new HttpException('active_subscription_required',409);
      if(row.plan_status!=='ACTIVE')throw new HttpException('active_plan_required',409);
      const addons=(await c.query(`select a.code,a.entitlements from billing.subscription_add_on sa join catalog.add_on_version a on a.id=sa.add_on_version_id where sa.subscription_id=$1 and sa.tenant_id=$2 and sa.status='ACTIVE' and a.status='ACTIVE' and (sa.effective_to is null or sa.effective_to>now()) order by a.code,a.version`,[row.subscription_id,row.tenant_id])).rows;
      const plan=object(row.plan_entitlements);const modules=new Set(strings(plan.modules));const quotas={...object(plan.quotas)};
      for(const add of addons){const ent=object(add.entitlements);for(const module of strings(ent.modules))modules.add(module);Object.assign(quotas,object(ent.quotas));}
      return{
        organizationId:String(row.platform_organization_id),
        snapshot:{tier:String(row.plan_code),modules:[...modules].sort(),quotas,addOns:addons.map((x:any)=>String(x.code)).sort(),billing:{tenantId:String(row.tenant_id),subscriptionId:String(row.subscription_id),invoiceId:String(row.id),invoiceNumber:String(row.invoice_number)}},
        tenantId:String(row.tenant_id),invoiceId:String(row.id),
      };
    });

    const base=process.env.PLATFORM_INTERNAL_URL||'http://platform-api:3001';const token=process.env.INTERNAL_API_TOKEN||'';
    const response=await fetch(`${base}/api/v1/internal/entitlements/sync`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:JSON.stringify(prepared)});
    const platform=await response.json().catch(()=>({}));
    if(!response.ok)throw new HttpException(platform?.message||platform?.error||`platform_entitlement_sync_${response.status}`,502);

    await adminTx(async c=>{await c.query(`insert into admin.audit_event(tenant_id,actor,action,object_type,object_id,after_data,reason,metadata) values($1,$2,'ENTITLEMENTS_APPLIED_FROM_PAID_INVOICE','billing.invoice',$3,$4::jsonb,'Paid invoice entitlement synchronization',$5::jsonb)`,[prepared.tenantId,String(actor.email||actor.id||'admin'),prepared.invoiceId,JSON.stringify(platform),JSON.stringify({platformOrganizationId:prepared.organizationId,entitlementSnapshotId:platform.entitlementSnapshotId})]);});
    return{status:'APPLIED_FROM_PAID_INVOICE',invoiceId:prepared.invoiceId,tenantId:prepared.tenantId,platform};
  }
}
