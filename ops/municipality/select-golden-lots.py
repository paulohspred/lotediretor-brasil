#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
import psycopg

DB=os.environ.get('PLATFORM_DATABASE_URL','')

def select(ibge:str,limit:int):
    if not DB:raise RuntimeError('PLATFORM_DATABASE_URL required')
    if not (ibge.isdigit() and len(ibge)==7):raise RuntimeError('ibge must have 7 digits')
    with psycopg.connect(DB) as c:
        rows=c.execute("""with ranked as (
          select p.id parcel_id,p.official_identifier,st_area(p.geom::geography) area_m2,
                 z.code zone_code,z.name zone_name,st_y(st_pointonsurface(p.geom)) lat,st_x(st_pointonsurface(p.geom)) lon,
                 row_number() over(partition by z.code order by md5(p.id::text)) rn
          from geo.parcel p join planning.zone z on z.municipality_ibge=p.municipality_ibge and st_intersects(p.geom,z.geom)
          join source.snapshot ps on ps.id=p.source_snapshot_id
          join source.snapshot zs on zs.id=z.source_snapshot_id
          where p.municipality_ibge=%s and p.valid_to is null and z.valid_to is null
            and ps.status='PUBLISHED' and ps.validation_status='PASS'
            and zs.status='PUBLISHED' and zs.validation_status='PASS'
        ) select * from ranked where rn=1 order by zone_code limit %s""",(ibge,limit)).fetchall()
    fields=['parcel_id','official_identifier','area_m2','zone_code','zone_name','lat','lon']
    return [dict(zip(fields,r)) for r in rows]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--ibge',default='3550308');ap.add_argument('--limit',type=int,default=20);ap.add_argument('--out');args=ap.parse_args()
    try:rows=select(args.ibge,max(1,min(args.limit,100)))
    except Exception as exc:print(f'golden lot selection failed: {exc}',file=sys.stderr);return 1
    cases=[]
    for n,row in enumerate(rows,1):
        cases.append({
          'case_code':f"{args.ibge}-ZONE-{row['zone_code']}-{n:02d}",
          'input_kind':'POINT',
          'input_payload':{'point':{'lat':float(row['lat']),'lon':float(row['lon'])}},
          'expected_official_reference':row['official_identifier'] or f"parcel:{row['parcel_id']}",
          'expected_parameters':{},
          'expected_zone_code':row['zone_code'],
          'parcel_area_m2':float(row['area_m2']),
          'status':'PENDING_HUMAN_REVIEW',
          'reviewer':None,
          'notes':'Auto-selected from QA-published parcel + zone snapshots. Parameters and official reference still require human verification; selection does not imply PASS.'
        })
    payload={'municipality_ibge':args.ibge,'status':'CANDIDATES_SELECTED_NOT_HOMOLOGATED','minimum_cases':10,'target_cases':20,'cases':cases}
    out=json.dumps(payload,ensure_ascii=False,indent=2)+'\n'
    if args.out:Path(args.out).write_text(out,encoding='utf-8')
    else:print(out,end='')
    return 0
if __name__=='__main__':sys.exit(main())
