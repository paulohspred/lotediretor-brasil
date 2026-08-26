import {Body,Controller,HttpException,Post,Req} from '@nestjs/common';
import {Pool} from 'pg';
import Redis from 'ioredis';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});
const redis=new Redis(process.env.VALKEY_URL||'redis://localhost:6379/0');

function plainObject(value:any){return value&&typeof value==='object'&&!Array.isArray(value)?value:{};}
function strings(value:any){return [...new Set((Array.isArray(value)?value:[]).map((x:any)=>String(x).trim()).filter(Boolean))].sort();}

function normalizedSnapshot(body:any){
  const requested=plainObject(body?.snapshot);
  const billing=plainObject(requested.billing);
  return {
    tier:String(requested.tier||'unassigned').slice(0,120),
    modules:strings(requested.modules),
    quotas:plainObject(requested.quotas),
    addOns:strings(requested.addOns),
    billing:{
      tenantId:String(billing.tenantId||'').slice(0,80),
      subscriptionId:String(billing.subscriptionId||'').slice(0,80),
      invoiceId:String(billing.invoiceId||'').slice(0,80),
      invoiceNumber:String(billing.invoiceNumber||'').slice(0,160),
    },
  };
}

async function refreshSessions(organizationId:string,snapshot:any){
  let cursor='0',updated=0;
  do{
    const [next,keys]=await redis.scan(cursor,'MATCH','session:*','COUNT',200);cursor=next;
    if(keys.length){
      const values=await redis.mget(...keys);
      for(let i=0;i<keys.length;i++){
        try{
          const session=JSON.parse(values[i]||'{}');
          if(String(session?.organizationId)!==organizationId)continue;
          session.entitlements=snapshot;
          await redis.set(keys[i],JSON.stringify(session),'KEEPTTL');
          updated++;
        }catch{}
      }
    }
  }while(cursor!=='0');
  return updated;
}

@Controller('api/v1/internal/entitlements')
export class EntitlementSyncController{
  @Post('sync')
  async sync(@Req() req:any,@Body() body:any){
    const expected=process.env.INTERNAL_API_TOKEN||'';
    if(!expected||req.headers?.['x-internal-token']!==expected)throw new HttpException('forbidden',403);
    const organizationId=String(body?.organizationId||'');
    if(!organizationId)throw new HttpException('organizationId_required',400);
    const snapshot=normalizedSnapshot(body);
    if(!snapshot.billing.invoiceId||!snapshot.billing.subscriptionId||!snapshot.billing.tenantId)throw new HttpException('billing_provenance_required',400);

    const c=await pool.connect();
    let id:string,replayed=false;
    try{
      await c.query('BEGIN');
      const org=await c.query(`select id,status from iam.organization where id=$1 for update`,[organizationId]);
      if(!org.rowCount||org.rows[0].status!=='ACTIVE')throw new HttpException('active_organization_required',409);
      const known=(await c.query(`select code from core.module where code=any($1::text[])`,[snapshot.modules])).rows.map((x:any)=>String(x.code));
      if(known.length!==snapshot.modules.length)throw new HttpException('unknown_entitlement_module',409);
      const current=await c.query(`select id,snapshot from core.entitlement_snapshot where organization_id=$1 and valid_from<=now() and (valid_to is null or valid_to>now()) order by valid_from desc limit 1 for update`,[organizationId]);
      if(current.rowCount&&JSON.stringify(current.rows[0].snapshot)===JSON.stringify(snapshot)){
        id=current.rows[0].id;replayed=true;
      }else{
        await c.query(`update core.entitlement_snapshot set valid_to=now() where organization_id=$1 and valid_to is null`,[organizationId]);
        const inserted=await c.query(`insert into core.entitlement_snapshot(organization_id,snapshot,valid_from) values($1,$2::jsonb,now()) returning id`,[organizationId,JSON.stringify(snapshot)]);
        id=inserted.rows[0].id;
      }
      await c.query('COMMIT');
    }catch(error){await c.query('ROLLBACK');throw error;}finally{c.release();}

    const sessionsUpdated=await refreshSessions(organizationId,snapshot);
    return{status:'SYNCHRONIZED',organizationId,entitlementSnapshotId:id,replayed,sessionsUpdated,snapshot};
  }
}
