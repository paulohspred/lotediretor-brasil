import {Controller,HttpException,Param,Req,Sse} from '@nestjs/common';
import {defer,Observable,switchMap} from 'rxjs';
import {Pool} from 'pg';
import {AuthService} from '../auth.service';
import {tenantTx} from '../common/tenant-db';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});
type JobSnapshot={id:string;kind:string;status:string;progress?:number|null;artifactKey?:string|null;updatedAt?:string|null};
const terminal=new Set(['COMPLETED','FAILED','CANCELLED','REJECTED']);

@Controller('api/v1')
export class JobEventsController{
  constructor(private readonly auth:AuthService){}
  private async session(req:any){const s:any=await this.auth.get(req.cookies?.ld_session);if(!s?.organizationId)throw new HttpException('unauthorized',401);return s;}
  private async snapshot(tenantId:string,id:string):Promise<JobSnapshot|null>{
    return tenantTx(pool,tenantId,async c=>{
      const report=await c.query(`select id,'REPORT' kind,status,artifact_key "artifactKey",completed_at::text "updatedAt" from report.report_run where id=$1 and tenant_id=$2`,[id,tenantId]);
      if(report.rowCount)return report.rows[0];
      const ingest=await c.query(`select id,'DOCUMENT_INGEST' kind,status,null::text "artifactKey",coalesce(completed_at,started_at,created_at)::text "updatedAt" from ingest.document_job where id=$1 and tenant_id=$2`,[id,tenantId]);
      if(ingest.rowCount)return ingest.rows[0];
      const aitec=await c.query(`select id,'AITEC' kind,status,null::text "artifactKey",coalesce(completed_at,started_at,created_at)::text "updatedAt" from aitec.job where id=$1 and tenant_id=$2`,[id,tenantId]);
      if(aitec.rowCount)return aitec.rows[0];
      return null;
    });
  }
  @Sse('events/jobs/:id')
  stream(@Req() req:any,@Param('id') id:string):Observable<any>{
    return defer(()=>this.session(req)).pipe(switchMap(s=>new Observable<any>(subscriber=>{
      let closed=false;let timer:any;
      const emit=async()=>{try{const current=await this.snapshot(s.organizationId,id);if(!current){subscriber.error(new HttpException('job_not_found',404));return;}subscriber.next({type:'job',id:current.id,data:current});if(terminal.has(String(current.status).toUpperCase()))subscriber.complete();}catch(error){subscriber.error(error);}};
      void emit();timer=setInterval(()=>{if(!closed)void emit();},Number(process.env.JOB_SSE_POLL_MS||1500));
      return()=>{closed=true;if(timer)clearInterval(timer);};
    })));
  }
}
