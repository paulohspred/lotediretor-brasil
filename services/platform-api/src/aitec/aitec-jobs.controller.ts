import {Body,Controller,Get,HttpException,Param,Post,Req} from '@nestjs/common';
import {Pool} from 'pg';
import {AuthService} from '../auth.service';
import {withIdempotency} from '../common/idempotency';
import {enqueueOutbox} from '../common/outbox';
import {tenantTx} from '../common/tenant-db';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});

type Session={id?:string;email?:string;roles?:string[];organizationId:string;entitlements?:{modules?:string[]}};

export const AITEC_JOB_OPERATIONS=new Set([
  'unit.solve','unit.compare',
  'terrain.tin','terrain.contours','terrain.plateaus','terrain.cut-fill',
  'building.solve','parking.basement','unit.room-graph','road.evaluate','environment.analyze','finance.calculate',
  'export.geojson','export.kml','export.kmz','export.dxf','export.ifc','export.xlsx','export.pdf','export.gltf','export.manifest',
  'ingest.dataset','ingest.geojson','ingest.kml','ingest.kmz','ingest.shapefile','ingest.gpkg','ingest.dxf','ingest.ifc',
  'optimization.pareto','optimization.diff',
]);

function plainObject(value:any){return value&&typeof value==='object'&&!Array.isArray(value)?value:{};}
function boundedPayload(args:any[],kwargs:any){
  let raw:string;
  try{raw=JSON.stringify({args,kwargs});}catch{throw new HttpException('aitec_job_payload_not_json',400);}
  if(Buffer.byteLength(raw,'utf8')>1024*1024)throw new HttpException('aitec_job_payload_too_large',413);
}

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
    const key=String(req.headers?.['idempotency-key']||'').trim();
    if(!key)throw new HttpException('idempotency_key_required',400);
    const operation=String(body?.operation||'').trim();
    if(!AITEC_JOB_OPERATIONS.has(operation))throw new HttpException('aitec_operation_not_allowed',400);
    const args=Array.isArray(body?.args)?body.args:[];
    const kwargs=plainObject(body?.kwargs);
    boundedPayload(args,kwargs);
    const constraintSnapshotId=body?.constraintSnapshotId?String(body.constraintSnapshotId):null;
    const seedRaw=body?.seed;
    const seed=seedRaw==null?null:Number(seedRaw);
    if(seed!==null&&(!Number.isInteger(seed)||seed<0||seed>2147483647))throw new HttpException('seed_invalid',400);

    const idem=await withIdempotency(pool,s.organizationId,'aitec.v20.job',key,async c=>{
      const project=await c.query(`select id,name,status from aitec.project where id=$1 and tenant_id=$2`,[projectId,s.organizationId]);
      if(!project.rowCount)throw new HttpException('aitec_project_not_found',404);
      if(constraintSnapshotId){
        const snapshot=await c.query(`select id from aitec.constraint_snapshot where id=$1 and project_id=$2 and tenant_id=$3`,[constraintSnapshotId,projectId,s.organizationId]);
        if(!snapshot.rowCount)throw new HttpException('constraint_snapshot_not_found',404);
      }
      const context:any={tenant_id:s.organizationId,project_id:projectId};
      if(constraintSnapshotId)context.constraint_snapshot_id=constraintSnapshotId;
      if(seed!==null)context.seed=seed;
      const r=await c.query(`insert into aitec.job(tenant_id,project_id,constraint_snapshot_id,operation,args,kwargs,execution_context,status,created_by)
        values($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7::jsonb,'QUEUED',$8)
        returning id,project_id,constraint_snapshot_id,operation,status,attempts,execution_context,next_attempt_at,created_at`,[
        s.organizationId,projectId,constraintSnapshotId,operation,JSON.stringify(args),JSON.stringify(kwargs),JSON.stringify(context),s.email||s.id,
      ]);
      const job=r.rows[0];
      await enqueueOutbox(c,'aitec.job.queued',{jobId:job.id,projectId,operation},{tenantId:s.organizationId,aggregateType:'aitec.job',aggregateId:job.id,dedupeKey:`aitec.job.queued:${job.id}`});
      return{...job,project:{id:project.rows[0].id,name:project.rows[0].name}};
    });
    return{...idem.value,idempotency:{key,replayed:idem.replayed,contract:'aitec.v20.job'}};
  }

  @Get('jobs/:jobId')
  async get(@Req() req:any,@Param('jobId') jobId:string){
    const s=await this.session(req);
    return tenantTx(pool,s.organizationId,async c=>{
      const r=await c.query(`select j.id,j.project_id,j.constraint_snapshot_id,j.operation,j.status,j.attempts,j.execution_context,j.solver_version,j.classification,j.professional_review_required,j.engine_response,j.error,j.created_by,j.created_at,j.next_attempt_at,j.started_at,j.completed_at,p.name project_name
        from aitec.job j join aitec.project p on p.id=j.project_id and p.tenant_id=j.tenant_id
        where j.id=$1 and j.tenant_id=$2`,[jobId,s.organizationId]);
      if(!r.rowCount)throw new HttpException('aitec_job_not_found',404);
      return r.rows[0];
    });
  }
}
