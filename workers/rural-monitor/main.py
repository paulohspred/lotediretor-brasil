from __future__ import annotations
import hashlib,json,os,time
import psycopg
from psycopg.types.json import Jsonb

DB=os.environ['PLATFORM_DATABASE_URL'];INTERVAL=max(60,int(os.getenv('RURAL_MONITOR_INTERVAL_SECONDS','900')));VERSION='19.0.0-rc.3'

def state_for(conn,asset_id):
    rows=conn.execute("""select code,official_identifier,source_snapshot_id,geometry_hash from (
      select lc.code,lf.official_identifier,lf.source_snapshot_id,encode(digest(st_asbinary(lf.geom),'sha256'),'hex') geometry_hash,lf.id::text sort_id
      from rural.asset a join rural.layer_feature lf on a.geom is not null and st_intersects(a.geom,lf.geom)
      join rural.layer_catalog lc on lc.code=lf.layer_code
      where a.id=%s and lf.source_snapshot_id in (select p.snapshot_id from source.publication p where p.status='ACTIVE')
      union all
      select rr.registry_type code,rr.official_identifier,rr.source_snapshot_id,
        case when rr.geom is null then null else encode(digest(st_asbinary(rr.geom),'sha256'),'hex') end geometry_hash,rr.id::text sort_id
      from rural.registry_record rr where rr.asset_id=%s and (rr.valid_from is null or rr.valid_from <= now()) and (rr.valid_to is null or rr.valid_to > now())
    ) x order by code,official_identifier nulls last,sort_id""",(asset_id,asset_id)).fetchall()
    state=[{'source':r[0],'id':r[1],'snapshotId':str(r[2]) if r[2] else None,'geometryHash':r[3]} for r in rows]
    raw=json.dumps(state,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode();return state,hashlib.sha256(raw).hexdigest()

def check_one(conn,monitor):
    mid,tenant,asset_id,mtype=monitor;state,h=state_for(conn,asset_id)
    prev=conn.execute("select state_hash,state,source_snapshot_ids from rural.monitor_checkpoint where monitor_id=%s order by checked_at desc limit 1",(mid,)).fetchone()
    snapshot_ids=sorted({x['snapshotId'] for x in state if x.get('snapshotId')})
    changed=bool(prev and prev[0]!=h);baseline=prev is None
    if baseline or changed:
        conn.execute("insert into rural.monitor_checkpoint(tenant_id,monitor_id,state_hash,state,source_snapshot_ids) values(%s,%s,%s,%s,%s::uuid[]) on conflict(monitor_id,state_hash) do nothing",(tenant,mid,h,Jsonb(state),snapshot_ids))
    if changed:
        summary={'previousHash':prev[0],'currentHash':h,'previousCount':len(prev[1] or []),'currentCount':len(state),'workerVersion':VERSION}
        before=(prev[2] or [None])[0] if prev[2] else None;after=snapshot_ids[0] if snapshot_ids else None
        event=conn.execute("insert into rural.monitor_event(tenant_id,monitor_id,event_type,status,before_snapshot_id,after_snapshot_id,change_summary) values(%s,%s,'SOURCE_INTERSECTION_CHANGED','NEW',%s,%s,%s) returning id",(tenant,mid,before,after,Jsonb(summary))).fetchone()[0]
        conn.execute("insert into notification.notification(tenant_id,kind,title,body,status,payload) values(%s,'RURAL_MONITOR_CHANGE','RE Rural: mudança detectada','Uma fonte monitorada mudou no imóvel rural.','UNREAD',%s)",(tenant,Jsonb({'monitorId':str(mid),'assetId':str(asset_id),'eventId':str(event),'stateHash':h})))
        conn.execute("insert into event.outbox(tenant_id,topic,aggregate_type,aggregate_id,dedupe_key,payload,status,next_attempt_at) values(%s,'rural.monitor.changed','rural.monitor',%s,%s,%s,'PENDING',now()) on conflict(dedupe_key) where dedupe_key is not null do nothing",(tenant,str(mid),f'rural.monitor.changed:{mid}:{h}',Jsonb({'monitorId':str(mid),'assetId':str(asset_id),'eventId':str(event),'stateHash':h})))
        conn.execute("update rural.monitor set last_checked_at=now(),last_change_at=now() where id=%s",(mid,))
    else:conn.execute("update rural.monitor set last_checked_at=now() where id=%s",(mid,))
    return changed

def run_cycle():
    with psycopg.connect(DB) as conn:
        monitors=conn.execute("select id,tenant_id,asset_id,monitor_type from rural.monitor where status='ACTIVE' order by last_checked_at nulls first limit 1000").fetchall()
        changed=0
        for m in monitors:
            try:
                with conn.transaction(): changed+=1 if check_one(conn,m) else 0
            except Exception as exc: print('monitor failed',m[0],exc,flush=True)
        print(json.dumps({'worker':'rural-monitor','version':VERSION,'checked':len(monitors),'changed':changed}),flush=True)

def main():
    while True:
        try:run_cycle()
        except Exception as exc:print('rural monitor loop error',exc,flush=True)
        time.sleep(INTERVAL)
if __name__=='__main__':main()
