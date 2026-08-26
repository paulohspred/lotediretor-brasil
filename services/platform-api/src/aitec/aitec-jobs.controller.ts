import {Body,Controller,Get,HttpException,Param,Post,Req} from '@nestjs/common';
import {Pool} from 'pg';
import {AuthService} from '../auth.service';
import {withIdempotency} from '../common/idempotency';
import {tenantTx} from '../common/tenant-db';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});

type Session={id?:string;email?:string;roles?:string[];organizationId:string;entitlements?:{modules?:string[]}};

@Controller('api/v1/aitec')
export class AitecJobsController{
  constructor(private readonly auth:AuthService){}

  private async session(req:any):Promise<Session>{
    const s=await this.auth.get(req.cookies?.ld_session) as Session|null;
    if(!s?.organizationId)throw new HttpException('unauthorized',401);
    const modules=Array.isArray(s.entitlements?.modules)?s.entitlements!.modules!:[];
    if(!s.roles?.includes('admin')&&!modules.includes('ai-tec'))throw new HttpException('module_not_entitled',403);
    return s;
  }

  @Post('projects/:projectId/jobs')
  async create(@Req() req:any,@Param('projectId') projectId:string,@Body() body:any){
    const s=await this.session(req);
    const operation=String(body?.operation||'').trim();
    if(!operation||!/^[a-z0-9.-]{3,80}$/i.test(operation))throw new HttpException('operation inválida',400);
    const args=Array.isArray(body?.args)?body.args:[];
    const kwargs=body?.kwargs&&typeof body.kwargs==='object'&&!Array.isArray(body.kwargs)?body.kwargs:{};
    const seed=body?.seed==null?null:Number(body.seed);
    if(seed!=null&&(!Number.isInteger(seed)||seed<0||seed>2147483647))throw new HttpException('seed inválido',400);
    const constraintSnapshotId=body?.constraintSnapshotId?String(body.constraintSnapshotId):null;
    const key=String(req.headers?.['idempotency-key']||'').trim()||undefined;

    const project=await tenantTx(pool,s.organizationId,async c=>{
      const r=await c.query(`select id,name,status from aitec.project where id=$1 and tenant_id=$2`,[projectId,s.organizationId]);
      if(!r.rowCount)throw new HttpException('aitec_project_not_found',404);
      if(constraintSnapshotId){
        const cs=await c.query(`select id from aitec.constraint_snapshot where id=$1 and project_id=$2 and tenant_id=$3`,[constraintSnapshotId,projectId,s.organizationId]);
        if(!cs.rowCount)throw new HttpException('constraint_snapshot_not_found',404);
      }
      return r.rows[0];
    });

    const idem=await withIdempotency(pool,s.organizationId,'aitec.v20.job',key,async c=>{
      const queued=await c.query(`insert into aitec.scenario(tenant_id,project_id,constraint_snapshot_id,solver_version,status,metrics)
        values($1,$2,$3,null,'QUEUED',$4::jsonb) returning id,project_id,constraint_snapshot_id,status,created_at`,[
        s.organizationId,projectId,constraintSnapshotId,JSON.stringify({operation,args,kwargs,seed,classification:'STUDY_PREPROJECT_NOT_EXECUTIVE'})
      ]);
      const job=queued.rows[0];
      const base=process.env.AITEC_ENGINE_INTERNAL_URL||'http://aitec-engine:8002';
      const token=process.env.INTERNAL_API_TOKEN||'';
      let response:Response;
      try{
        response=await fetch(`${base}/aitec/v20/execute/${encodeURIComponent(operation)}`,{
          method:'POST',headers:{'content-type':'application/json','x-internal-token':token},
          body:JSON.stringify({args,kwargs,context:{tenant_id:s.organizationId,project_id:projectId,constraint_snapshot_id:constraintSnapshotId||undefined,seed:seed??undefined}}),
        });
      }catch(exc:any){
        await c.query(`update aitec.scenario set status='FAILED',metrics=metrics||$2::jsonb where id=$1`,[job.id,JSON.stringify({error:'aitec_engine_unreachable',detail:String(exc?.message||exc).slice(0,500)})]);
        throw new HttpException('aitec_engine_unreachable',502);
      }
      const data=await response.json().catch(()=>({} as any)) as any;
      if(!response.ok){
        await c.query(`update aitec.scenario set status='FAILED',metrics=metrics||$2::jsonb where id=$1`,[job.id,JSON.stringify({engineStatus:response.status,error:data?.detail||data?.message||'solver_failed'})]);
        throw new HttpException(data?.detail||data?.message||`aitec_engine_${response.status}`,response.status===404?422:502);
      }
      const solverVersion=String(data?.solver_version||'unknown');
      const metrics={operation,args,kwargs,seed,classification:data?.classification||'STUDY_PREPROJECT_NOT_EXECUTIVE',professional_review_required:data?.professional_review_required!==false,result:data?.result??null,limitations:Array.isArray(data?.limitations)?data.limitations:[]};
      const done=await c.query(`update aitec.scenario set status='COMPLETED',solver_version=$2,metrics=$3::jsonb where id=$1 returning id,project_id,constraint_snapshot_id,solver_version,status,metrics,created_at`,[job.id,solverVersion,JSON.stringify(metrics)]);
      return done.rows[0];
    });
    return{...idem.value,project:{id:project.id,name:project.name},idempotency:{replayed:idem.replayed,key:key||null,contract:'aitec.v20.job'}};
  }

  @Get('jobs/:jobId')
  async get(@Req() req:any,@Param('jobId') jobId:string){
    const s=await this.session(req);
    return tenantTx(pool,s.organizationId,async c=>{
      const r=await c.query(`select s.id,s.project_id,s.constraint_snapshot_id,s.solver_version,s.status,s.metrics,s.artifact_key,s.created_at,p.name project_name
        from aitec.scenario s join aitec.project p on p.id=s.project_id and p.tenant_id=s.tenant_id
        where s.id=$1 and s.tenant_id=$2`,[jobId,s.organizationId]);
      if(!r.rowCount)throw new HttpException('aitec_job_not_found',404);
      return r.rows[0];
    });
  }
}
