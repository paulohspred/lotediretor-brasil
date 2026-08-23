import {Body,Controller,Get,HttpException,HttpStatus,Param,Post,Req} from '@nestjs/common';
import {Pool} from 'pg';
import Redis from 'ioredis';

const pool=new Pool({connectionString:process.env.CONTROL_DATABASE_URL});
const redis=new Redis(process.env.VALKEY_URL||'redis://localhost:6379/0');
import {CONTROL_VERSION} from './version';
const VERSION=CONTROL_VERSION;

async function requireAdmin(req:any){
  const sid=req.cookies?.ld_session;if(!sid)throw new HttpException('unauthorized',HttpStatus.UNAUTHORIZED);
  const raw=await redis.get(`session:${sid}`);if(!raw)throw new HttpException('unauthorized',HttpStatus.UNAUTHORIZED);
  const session=JSON.parse(raw);if(!session.roles?.includes('admin'))throw new HttpException('forbidden',HttpStatus.FORBIDDEN);return session;
}

async function platform(path:string){
  const base=process.env.PLATFORM_INTERNAL_URL||'http://platform-api:3001';
  const token=process.env.INTERNAL_API_TOKEN||'';
  const r=await fetch(`${base}${path}`,{headers:{'x-internal-token':token}});
  const data=await r.json().catch(()=>({}));
  if(!r.ok)throw new HttpException(data?.message||data?.error||`platform_${r.status}`,502);
  return data;
}

@Controller('control/v1')
export class ControlV7Controller{
  @Get('ops/readiness')
  async readiness(@Req() req:any){
    await requireAdmin(req);
    const started=Date.now();
    const checks:any[]=[];
    try{await pool.query('select 1');checks.push({service:'control-db',status:'UP'});}catch(e:any){checks.push({service:'control-db',status:'DOWN',error:e?.message});}
    try{const p=await platform('/api/v1/internal/system/readiness');checks.push({service:'platform-api',status:'UP',details:p});}catch(e:any){checks.push({service:'platform-api',status:'DOWN',error:e?.message});}
    const overall=checks.every(x=>x.status==='UP')?'READY':'DEGRADED';
    await pool.query(`insert into ops.check_run(check_type,environment,status,summary,completed_at) values('READINESS',$1,$2,$3::jsonb,now())`,[process.env.NODE_ENV||'local',overall,JSON.stringify({checks,durationMs:Date.now()-started})]);
    return{version:VERSION,status:overall,checks,durationMs:Date.now()-started};
  }

  @Get('ops/incidents')
  async incidents(@Req() req:any){await requireAdmin(req);return{items:(await pool.query(`select id,severity,service,title,status,details,opened_at,resolved_at from ops.incident order by opened_at desc limit 200`)).rows};}

  @Post('ops/incidents')
  async createIncident(@Req() req:any,@Body() body:any){const s=await requireAdmin(req);const r=await pool.query(`insert into ops.incident(severity,service,title,status,details) values($1,$2,$3,'OPEN',$4::jsonb) returning *`,[String(body?.severity||'SEV3'),body?.service||null,String(body?.title||'Incidente'),JSON.stringify(body?.details||{})]);await pool.query(`insert into admin.audit_event(actor,action,object_type,object_id,after_data,reason) values($1,'INCIDENT_CREATED','ops.incident',$2,$3::jsonb,$4)`,[s.email||s.id,r.rows[0].id,JSON.stringify(r.rows[0]),body?.reason||null]);return r.rows[0];}

  @Post('ops/incidents/:id/resolve')
  async resolveIncident(@Req() req:any,@Param('id') id:string,@Body() body:any){const s=await requireAdmin(req);const r=await pool.query(`update ops.incident set status='RESOLVED',resolved_at=now(),details=details||$2::jsonb where id=$1 and status<>'RESOLVED' returning *`,[id,JSON.stringify({resolution:body?.resolution||null})]);if(!r.rowCount)throw new HttpException('incident_not_found_or_resolved',404);await pool.query(`insert into admin.audit_event(actor,action,object_type,object_id,after_data,reason) values($1,'INCIDENT_RESOLVED','ops.incident',$2,$3::jsonb,$4)`,[s.email||s.id,id,JSON.stringify(r.rows[0]),body?.reason||null]);return r.rows[0];}

  @Get('data-ops/quality')
  async quality(@Req() req:any){await requireAdmin(req);return platform('/api/v1/internal/data-ops/quality');}

  @Get('catalog/plans')
  async plans(@Req() req:any){await requireAdmin(req);return{items:(await pool.query(`select id,code,version,name,currency,monthly_cents,annual_cents,status,entitlements,created_at from catalog.plan_version order by code,version desc`)).rows};}

  @Post('catalog/plans')
  async createPlan(@Req() req:any,@Body() body:any){const s=await requireAdmin(req);const code=String(body?.code||'').trim();if(!code)throw new HttpException('code obrigatório',400);const r=await pool.query(`insert into catalog.plan_version(code,version,name,currency,monthly_cents,annual_cents,status,entitlements) select $1,coalesce(max(version),0)+1,$2,'BRL',$3,$4,'DRAFT',$5::jsonb from catalog.plan_version where code=$1 returning *`,[code,String(body?.name||code),body?.monthlyCents??null,body?.annualCents??null,JSON.stringify(body?.entitlements||{})]);await pool.query(`insert into admin.audit_event(actor,action,object_type,object_id,after_data,reason) values($1,'PLAN_VERSION_CREATED','catalog.plan_version',$2,$3::jsonb,$4)`,[s.email||s.id,r.rows[0].id,JSON.stringify(r.rows[0]),body?.reason||null]);return r.rows[0];}

  @Post('catalog/plans/:id/request-activation')
  async requestPlanActivation(@Req() req:any,@Param('id') id:string,@Body() body:any){const s=await requireAdmin(req);const p=await pool.query(`select id,code,version from catalog.plan_version where id=$1`,[id]);if(!p.rowCount)throw new HttpException('plan_not_found',404);const approval=await pool.query(`insert into admin.approval(action,object_type,object_id,requested_by,status,reason) values('ACTIVATE_PLAN','catalog.plan_version',$1,$2,'PENDING',$3) returning *`,[id,s.email||s.id,body?.reason||null]);return{plan:p.rows[0],approval:approval.rows[0]};}

  @Get('deployments')
  async deployments(@Req() req:any){await requireAdmin(req);return{items:(await pool.query(`select d.id,d.environment,d.status,d.artifact_digest,d.approved_by,d.deployed_at,d.rolled_back_at,d.metadata,d.created_at,r.version from release.deployment d left join release.release r on r.id=d.release_id order by d.created_at desc limit 100`)).rows};}

  @Post('deployments')
  async createDeployment(@Req() req:any,@Body() body:any){const s=await requireAdmin(req);const version=String(body?.version||CONTROL_VERSION);const environment=String(body?.environment||'staging');const rel=await pool.query(`insert into release.release(version,environment,status,artifact_digest) values($1,$2,'BUILT',$3) on conflict(version,environment) do update set artifact_digest=excluded.artifact_digest returning id,version,environment`,[version,environment,body?.artifactDigest||null]);const d=await pool.query(`insert into release.deployment(release_id,environment,status,artifact_digest,metadata) values($1,$2,'BUILT',$3,$4::jsonb) returning *`,[rel.rows[0].id,environment,body?.artifactDigest||null,JSON.stringify(body?.metadata||{})]);const approval=await pool.query(`insert into admin.approval(action,object_type,object_id,requested_by,status,reason) values('PROMOTE_DEPLOYMENT','release.deployment',$1,$2,'PENDING',$3) returning id,status`,[d.rows[0].id,s.email||s.id,body?.reason||'Deployment promotion']);return{deployment:d.rows[0],approval:approval.rows[0]};}
  @Get('billing/webhooks')
  async billingWebhooks(@Req() req:any){await requireAdmin(req);return{items:(await pool.query(`select id,provider,event_key,verified,request_id,resource_id,topic,received_at,processing_at,processed_at,error from billing.webhook_event order by received_at desc limit 200`)).rows};}

  @Get('security/posture')
  async securityPosture(@Req() req:any){
    await requireAdmin(req);const [pending,openIncidents,unverified,failedWebhooks]=await Promise.all([pool.query(`select count(*)::int n from admin.approval where status='PENDING'`),pool.query(`select count(*)::int n from ops.incident where status<>'RESOLVED'`),pool.query(`select count(*)::int n from billing.webhook_event where verified=false`),pool.query(`select count(*)::int n from billing.webhook_event where error is not null`)]);
    return{version:VERSION,controls:{adminMfaPolicy:'KEYCLOAK_ROLE_POLICY_CONFIGURED',makerChecker:true,privateObjectStorage:true,webhookSignatureRequired:true,internalTokenConfigured:Boolean(process.env.INTERNAL_API_TOKEN),databaseRls:'POLICIES_DEFINED_APP_ROLE_REQUIRED_FOR_PRODUCTION_FORCE'},counters:{pendingApprovals:pending.rows[0]?.n||0,openIncidents:openIncidents.rows[0]?.n||0,unverifiedWebhooks:unverified.rows[0]?.n||0,failedWebhooks:failedWebhooks.rows[0]?.n||0},limitations:['Execute tenant isolation tests using the production non-owner PostgreSQL role before release.']};
  }

  @Get('audit')
  async audit(@Req() req:any){await requireAdmin(req);return{items:(await pool.query(`select id,actor,action,object_type,object_id,reason,created_at from admin.audit_event order by created_at desc limit 300`)).rows};}

}
