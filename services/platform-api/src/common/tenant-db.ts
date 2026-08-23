import {Pool,PoolClient,QueryResult,QueryResultRow} from 'pg';

export async function tenantTx<T>(pool:Pool,tenantId:string,fn:(client:PoolClient)=>Promise<T>):Promise<T>{
  if(!tenantId)throw new Error('tenant_id_required');
  const client=await pool.connect();
  try{
    await client.query('BEGIN');
    await client.query(`select set_config('app.tenant_id',$1,true)`,[tenantId]);
    const result=await fn(client);
    await client.query('COMMIT');
    return result;
  }catch(error){
    await client.query('ROLLBACK');
    throw error;
  }finally{
    client.release();
  }
}

export async function tenantQuery<T extends QueryResultRow=QueryResultRow>(pool:Pool,tenantId:string,text:string,values:any[]=[]):Promise<QueryResult<T>>{
  return tenantTx(pool,tenantId,client=>client.query<T>(text,values));
}
