from __future__ import annotations
import os,time,psycopg
from psycopg.types.json import Jsonb
DB=os.environ['PLATFORM_DATABASE_URL'];INTERVAL=int(os.getenv('GEO_QUALITY_INTERVAL_SECONDS','3600'))

def check_one():
  with psycopg.connect(DB) as c:
    row=c.execute("""select s.id,s.source_id,r.code from source.snapshot s join source.registry r on r.id=s.source_id
      where s.status='PUBLISHED' and exists(select 1 from rural.layer_feature f where f.source_snapshot_id=s.id)
      order by coalesce(s.published_at,s.ingested_at) desc limit 1""").fetchone()
    if not row:return False
    snapshot_id,source_id,code=row
    stats=c.execute("""select count(*)::bigint total,count(*) filter(where not st_isvalid(geom))::bigint invalid,
      count(*) filter(where st_srid(geom)<>4326)::bigint wrong_srid from rural.layer_feature where source_snapshot_id=%s""",(snapshot_id,)).fetchone()
    total,invalid,wrong=map(int,stats);status='PASS' if invalid==0 and wrong==0 and total>0 else 'FAIL'
    c.execute("""insert into data_quality.result(source_id,snapshot_id,check_code,severity,status,expected,observed)
      values(%s,%s,'geometry_validity','ERROR',%s,%s,%s)
      on conflict(snapshot_id,check_code) do update set status=excluded.status,expected=excluded.expected,observed=excluded.observed,checked_at=now()""",
      (source_id,snapshot_id,status,Jsonb({'invalid':0,'wrong_srid':0,'min_features':1}),Jsonb({'total':total,'invalid':invalid,'wrong_srid':wrong})))
    if status=='FAIL':c.execute("update source.snapshot set validation_status='FAIL' where id=%s",(snapshot_id,))
    c.commit();print('geo quality',code,snapshot_id,status,{'total':total,'invalid':invalid,'wrong_srid':wrong},flush=True);return True

def main():
 while True:
  try:check_one()
  except Exception as exc:print('geo quality error',repr(exc),flush=True)
  time.sleep(INTERVAL)
if __name__=='__main__':main()
