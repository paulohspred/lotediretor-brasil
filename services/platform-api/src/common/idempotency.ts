import {HttpException} from '@nestjs/common';
import {Pool,PoolClient} from 'pg';

export type IdempotentResult<T>={value:T;replayed:boolean};

function ttlHours(){
  const parsed=Number(process.env.IDEMPOTENCY_TTL_HOURS||24);
  if(!Number.isFinite(parsed))return 24;
  return Math.min(168,Math.max(1,Math.trunc(parsed)));
}

export async function withIdempotency<T>(pool:Pool,tenantId:string,scope:string,key:string|undefined,fn:(c:PoolClient)=>Promise<T>):Promise<IdempotentResult<T>>{
  const c=await pool.connect();
  try{
    await c.query('BEGIN');
    await c.query(`select set_config('app.tenant_id',$1,true)`,[tenantId]);
    if(!key){const value=await fn(c);await c.query('COMMIT');return{value,replayed:false};}
    if(key.length>160)throw new HttpException({code:'idempotency_key_too_long',message:'Idempotency-Key excede 160 caracteres'},400);

    const claim=()=>c.query(`insert into api.idempotency_key(tenant_id,scope,idempotency_key,status,response,completed_at,expires_at)
      values($1,$2,$3,'IN_PROGRESS',null,null,now()+($4::int*interval '1 hour'))
      on conflict (tenant_id,scope,idempotency_key) do update
      set status='IN_PROGRESS',response=null,created_at=now(),completed_at=null,expires_at=excluded.expires_at
      where api.idempotency_key.expires_at<=now()
      returning status,response`,[tenantId,scope,key,ttlHours()]);

    let claimed=await claim();
    if(!claimed.rowCount){
      const found=await c.query(`select response,status from api.idempotency_key
        where tenant_id=$1 and scope=$2 and idempotency_key=$3 and expires_at>now()
        for update`,[tenantId,scope,key]);
      if(found.rowCount&&found.rows[0].status==='COMPLETED'){
        await c.query('COMMIT');
        return{value:found.rows[0].response as T,replayed:true};
      }
      // A cleanup transaction can delete the conflicting row between the UPSERT and
      // this SELECT. One retry closes that race without allowing two owners to run fn().
      if(!found.rowCount)claimed=await claim();
      if(!claimed.rowCount)throw new HttpException({code:'idempotency_in_progress',message:'Comando idempotente ainda em processamento'},409);
    }

    const value=await fn(c);
    await c.query(`update api.idempotency_key
      set status='COMPLETED',response=$4::jsonb,completed_at=now()
      where tenant_id=$1 and scope=$2 and idempotency_key=$3`,[tenantId,scope,key,JSON.stringify(value)]);
    await c.query('COMMIT');
    return{value,replayed:false};
  }catch(e){
    await c.query('ROLLBACK');
    throw e;
  }finally{
    c.release();
  }
}
