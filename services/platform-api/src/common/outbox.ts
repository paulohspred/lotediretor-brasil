import {PoolClient} from 'pg';

export async function enqueueOutbox(c:PoolClient,topic:string,payload:unknown,options?:{tenantId?:string|null;aggregateType?:string|null;aggregateId?:string|null;dedupeKey?:string|null}){
  const r=await c.query(`insert into event.outbox(tenant_id,topic,aggregate_type,aggregate_id,dedupe_key,payload,status,next_attempt_at)
    values($1,$2,$3,$4,$5,$6::jsonb,'PENDING',now())
    on conflict(dedupe_key) where dedupe_key is not null do update set payload=excluded.payload
    returning id,topic,status,created_at`,[
      options?.tenantId||null,topic,options?.aggregateType||null,options?.aggregateId||null,options?.dedupeKey||null,JSON.stringify(payload??{})
    ]);
  return r.rows[0];
}
