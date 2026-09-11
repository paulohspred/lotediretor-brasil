import {hostname} from 'node:os';
import {connect,JSONCodec,JetStreamClient,NatsConnection} from 'nats';
import {Pool} from 'pg';

const VERSION='19.0.0-rc.3';
const STREAM='LOTEDIRETOR_EVENTS';
const SUBJECTS=['source.>','analysis.>','report.>','solar.>','aitec.>','document.>','municipality.>','billing.>'];
const databaseUrl=process.env.PLATFORM_EVENT_DATABASE_URL||'';
if(!databaseUrl)throw new Error('PLATFORM_EVENT_DATABASE_URL is required');
const pool=new Pool({connectionString:databaseUrl,max:Number(process.env.EVENT_DB_POOL_MAX||5)});
const jc=JSONCodec();
const dispatcherId=(process.env.EVENT_DISPATCHER_ID||`${hostname()}:${process.pid}`).slice(0,255);
let nc:NatsConnection|null=null;
let js:JetStreamClient|null=null;

function boundedInt(raw:string|undefined,fallback:number,min:number,max:number){
  const value=Number(raw??fallback);
  return Number.isFinite(value)?Math.min(max,Math.max(min,Math.trunc(value))):fallback;
}

const batchSize=()=>boundedInt(process.env.EVENT_BATCH_SIZE,50,1,500);
const claimLeaseSeconds=()=>boundedInt(process.env.EVENT_CLAIM_LEASE_SECONDS,120,15,3600);
const pollMs=()=>boundedInt(process.env.EVENT_POLL_MS,1000,100,60000);

async function eventBus(){
  if(nc&&!nc.isClosed()&&js)return js;
  nc=await connect({servers:process.env.NATS_URL||'nats://nats:4222',name:`lotediretor-event-dispatcher-${VERSION}`});
  const jsm=await nc.jetstreamManager();
  try{await jsm.streams.info(STREAM);}catch{
    await jsm.streams.add({name:STREAM,subjects:SUBJECTS,storage:'file' as any,retention:'limits' as any,discard:'old' as any,max_msgs:-1,max_bytes:-1,max_age:0,duplicate_window:120_000_000_000 as any});
  }
  js=nc.jetstream();
  return js;
}

async function claimBatch(){
  const c=await pool.connect();
  try{
    await c.query('BEGIN');
    const r=await c.query(`select id,tenant_id,topic,aggregate_type,aggregate_id,payload,attempts,created_at
      from event.outbox
      where (
        (status in ('PENDING','FAILED') and next_attempt_at<=now())
        or (status='PUBLISHING' and (lease_until is null or lease_until<=now()))
      )
      order by created_at
      for update skip locked
      limit $1`,[batchSize()]);
    if(r.rowCount){
      await c.query(`update event.outbox
        set status='PUBLISHING',attempts=attempts+1,claimed_by=$2,claimed_at=now(),lease_until=now()+($3::int*interval '1 second')
        where id=any($1::uuid[])`,[r.rows.map(x=>x.id),dispatcherId,claimLeaseSeconds()]);
    }
    await c.query('COMMIT');
    return r.rows;
  }catch(e){
    await c.query('ROLLBACK');
    throw e;
  }finally{
    c.release();
  }
}

async function markPublished(id:string,stream:string,sequence:number){
  const result=await pool.query(`update event.outbox
    set status='PUBLISHED',published_at=now(),last_error=null,publish_metadata=$2::jsonb,
        claimed_by=null,claimed_at=null,lease_until=null
    where id=$1 and status='PUBLISHING' and claimed_by=$3`,[id,JSON.stringify({stream,sequence}),dispatcherId]);
  return Boolean(result.rowCount);
}

async function markFailed(id:string,error:unknown,attempts:number){
  const delay=Math.min(300,Math.max(2,2**Math.min(attempts,8)));
  const result=await pool.query(`update event.outbox
    set status='FAILED',last_error=$2,next_attempt_at=now()+($3::int*interval '1 second'),
        claimed_by=null,claimed_at=null,lease_until=null
    where id=$1 and status='PUBLISHING' and claimed_by=$4`,[
      id,String((error as any)?.message||error).slice(0,2000),delay,dispatcherId
    ]);
  return Boolean(result.rowCount);
}

async function dispatchOnce(){
  // Establish the transport before claiming DB work. If NATS is unavailable, no row is
  // unnecessarily held in PUBLISHING while the dispatcher reconnects.
  const bus=await eventBus();
  const rows=await claimBatch();
  if(!rows.length)return 0;
  for(const row of rows){
    try{
      const envelope={id:row.id,topic:row.topic,tenant_id:row.tenant_id,aggregate_type:row.aggregate_type,aggregate_id:row.aggregate_id,occurred_at:row.created_at,version:1,payload:row.payload};
      const ack=await bus.publish(row.topic,jc.encode(envelope),{msgID:String(row.id)});
      const owned=await markPublished(row.id,ack.stream,ack.seq);
      if(!owned)console.warn('event_publish_claim_lost',JSON.stringify({id:row.id,dispatcherId}));
    }catch(error){
      const owned=await markFailed(row.id,error,row.attempts+1);
      if(!owned)console.warn('event_failure_claim_lost',JSON.stringify({id:row.id,dispatcherId}));
    }
  }
  return rows.length;
}

async function main(){
  console.log(JSON.stringify({service:'event-dispatcher',version:VERSION,transport:'NATS_JETSTREAM',stream:STREAM,dispatcherId,claimLeaseSeconds:claimLeaseSeconds(),status:'STARTING'}));
  let stopped=false;
  const stop=async()=>{stopped=true;try{await nc?.drain();}catch{}await pool.end();};
  process.on('SIGTERM',()=>void stop());
  process.on('SIGINT',()=>void stop());
  while(!stopped){
    try{
      const n=await dispatchOnce();
      if(!n)await new Promise(r=>setTimeout(r,pollMs()));
    }catch(error){
      console.error('event_dispatch_error',error);
      await new Promise(r=>setTimeout(r,3000));
    }
  }
}

main().catch(e=>{console.error(e);process.exit(1)});
