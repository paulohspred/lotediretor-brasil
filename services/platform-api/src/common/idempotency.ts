import {HttpException} from '@nestjs/common';
import {Pool,PoolClient} from 'pg';

export type IdempotentResult<T>={value:T;replayed:boolean};

export async function withIdempotency<T>(pool:Pool,tenantId:string,scope:string,key:string|undefined,fn:(c:PoolClient)=>Promise<T>):Promise<IdempotentResult<T>>{
  const c=await pool.connect();
  try{
    await c.query('BEGIN');
    await c.query(`select set_config('app.tenant_id',$1,true)`,[tenantId]);
    if(!key){const value=await fn(c);await c.query('COMMIT');return{value,replayed:false};}
    if(key.length>160)throw new HttpException({code:'idempotency_key_too_long',message:'Idempotency-Key excede 160 caracteres'},400);
    const inserted=await c.query(`insert into api.idempotency_key(tenant_id,scope,idempotency_key,status,expires_at) values($1,$2,$3,'IN_PROGRESS',now()+interval '24 hours') on conflict do nothing returning idempotency_key`,[tenantId,scope,key]);
    if(!inserted.rowCount){
      const found=await c.query(`select response,status from api.idempotency_key where tenant_id=$1 and scope=$2 and idempotency_key=$3 and expires_at>now() for update`,[tenantId,scope,key]);
      if(found.rowCount&&found.rows[0].status==='COMPLETED'){await c.query('COMMIT');return{value:found.rows[0].response as T,replayed:true};}
      throw new HttpException({code:'idempotency_in_progress',message:'Comando idempotente ainda em processamento'},409);
    }
    const value=await fn(c);
    await c.query(`update api.idempotency_key set status='COMPLETED',response=$4::jsonb,completed_at=now() where tenant_id=$1 and scope=$2 and idempotency_key=$3`,[tenantId,scope,key,JSON.stringify(value)]);
    await c.query('COMMIT');return{value,replayed:false};
  }catch(e){await c.query('ROLLBACK');throw e;}finally{c.release();}
}
