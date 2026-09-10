import {createHash} from 'crypto';
import {Pool} from 'pg';
import {readdirSync,readFileSync} from 'fs';
import {join} from 'path';

export async function runMigrations(url:string,dir:string){
  const pool=new Pool({connectionString:url});
  try{
    await pool.query(`CREATE TABLE IF NOT EXISTS public.schema_migrations(
      name text primary key,
      checksum_sha256 text,
      applied_at timestamptz not null default now()
    )`);
    await pool.query('ALTER TABLE public.schema_migrations ADD COLUMN IF NOT EXISTS checksum_sha256 text');

    for(const name of readdirSync(dir).filter(x=>x.endsWith('.sql')).sort()){
      const sql=readFileSync(join(dir,name),'utf8');
      const checksum=createHash('sha256').update(sql,'utf8').digest('hex');
      const hit=await pool.query('select checksum_sha256 from public.schema_migrations where name=$1',[name]);
      if(hit.rowCount){
        const recorded=hit.rows[0].checksum_sha256 as string|null;
        if(recorded&&recorded!==checksum)throw new Error(`migration_checksum_mismatch:${name}:recorded=${recorded}:current=${checksum}`);
        if(!recorded){
          await pool.query('update public.schema_migrations set checksum_sha256=$2 where name=$1 and checksum_sha256 is null',[name,checksum]);
          console.warn('migration checksum adopted for legacy row',name,checksum);
        }
        continue;
      }

      const c=await pool.connect();
      try{
        await c.query('begin');
        await c.query(sql);
        await c.query('insert into public.schema_migrations(name,checksum_sha256) values($1,$2)',[name,checksum]);
        await c.query('commit');
        console.log('migration',name,checksum);
      }catch(e){
        await c.query('rollback');
        throw e;
      }finally{c.release();}
    }
  }finally{
    await pool.end();
  }
}
