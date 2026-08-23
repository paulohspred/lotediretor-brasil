import {connect,JSONCodec,JetStreamClient,NatsConnection} from 'nats';
import {Pool} from 'pg';

const VERSION='19.0.0-rc.3';
const STREAM='LOTEDIRETOR_EVENTS';
const SUBJECTS=['source.>','analysis.>','report.>','solar.>','aitec.>','document.>','municipality.>','billing.>'];
const databaseUrl=process.env.PLATFORM_EVENT_DATABASE_URL||'';
if(!databaseUrl)throw new Error('PLATFORM_EVENT_DATABASE_URL is required');
const pool=new Pool({connectionString:databaseUrl,max:Number(process.env.EVENT_DB_POOL_MAX||5)});
const jc=JSONCodec();
let nc:NatsConnection|null=null;
let js:JetStreamClient|null=null;

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
      where status in ('PENDING','FAILED') and next_attempt_at<=now()
      order by created_at
      for update skip locked
      limit $1`,[Number(process.env.EVENT_BATCH_SIZE||50)]);
    if(r.rowCount)await c.query(`update event.outbox set status='PUBLISHING',attempts=attempts+1 where id=any($1::uuid[])`,[r.rows.map(x=>x.id)]);
    await c.query('COMMIT');
    return r.rows;
  }catch(e){await c.query('ROLLBACK');throw e;}finally{c.release();}
}

async function markPublished(id:string,stream:string,sequence:number){
  await pool.query(`update event.outbox set status='PUBLISHED',published_at=now(),last_error=null,publish_metadata=$2::jsonb where id=$1`,[id,JSON.stringify({stream,sequence})]);
}
async function markFailed(id:string,error:unknown,attempts:number){
  const delay=Math.min(300,Math.max(2,2**Math.min(attempts,8)));
  await pool.query(`update event.outbox set status='FAILED',last_error=$2,next_attempt_at=now()+($3::text||' seconds')::interval where id=$1`,[id,String((error as any)?.message||error).slice(0,2000),String(delay)]);
}

async function dispatchOnce(){
  const rows=await claimBatch();if(!rows.length)return 0;
  const bus=await eventBus();
  for(const row of rows){
    try{
      const envelope={id:row.id,topic:row.topic,tenant_id:row.tenant_id,aggregate_type:row.aggregate_type,aggregate_id:row.aggregate_id,occurred_at:row.created_at,version:1,payload:row.payload};
      const ack=await bus.publish(row.topic,jc.encode(envelope),{msgID:String(row.id)});
      await markPublished(row.id,ack.stream,ack.seq);
    }catch(error){await markFailed(row.id,error,row.attempts+1);}
  }
  return rows.length;
}

async function main(){
  console.log(JSON.stringify({service:'event-dispatcher',version:VERSION,transport:'NATS_JETSTREAM',stream:STREAM,status:'STARTING'}));
  let stopped=false;
  const stop=async()=>{stopped=true;try{await nc?.drain();}catch{}await pool.end();};
  process.on('SIGTERM',()=>void stop());process.on('SIGINT',()=>void stop());
  while(!stopped){
    try{const n=await dispatchOnce();if(!n)await new Promise(r=>setTimeout(r,Number(process.env.EVENT_POLL_MS||1000)));}
    catch(error){console.error('event_dispatch_error',error);await new Promise(r=>setTimeout(r,3000));}
  }
}
main().catch(e=>{console.error(e);process.exit(1)});
