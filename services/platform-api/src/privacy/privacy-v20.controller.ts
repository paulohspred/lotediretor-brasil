import {Body,Controller,Get,HttpException,Param,Post,Put,Query,Req} from '@nestjs/common';
import {Pool} from 'pg';
import {AuthService} from '../auth.service';
import {tenantTx} from '../common/tenant-db';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});
const REQUEST_TYPES=new Set(['ACCESS','PORTABILITY','RECTIFICATION','RESTRICTION','ERASURE']);
const TERMINAL=new Set(['COMPLETED','REJECTED']);
const PROTECTED_CATEGORIES=new Set(['AUDIT_TRAIL','LEGAL_EVIDENCE','SOURCE_PROVENANCE']);

function text(v:any,max=2000){return String(v??'').trim().slice(0,max);}
function uuidish(v:any){const s=text(v,80);if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(s))throw new HttpException('uuid inválido',400);return s;}

@Controller('api/v1/privacy/v20')
export class PrivacyV20Controller{
  constructor(private readonly auth:AuthService){}
  private async session(req:any,admin=false){const s=await this.auth.get(req.cookies?.ld_session);if(!s?.organizationId||!s?.id)throw new HttpException('unauthorized',401);if(admin&&!s.roles?.includes('admin'))throw new HttpException('forbidden',403);return s;}

  @Post('requests')
  async createRequest(@Req() req:any,@Body() body:any){
    const s=await this.session(req);const requestType=text(body?.requestType,32).toUpperCase();if(!REQUEST_TYPES.has(requestType))throw new HttpException('requestType inválido',400);
    return tenantTx(pool,s.organizationId,async c=>{
      const existing=await c.query(`select id,request_type,status,created_at from privacy.subject_request where tenant_id=$1 and subject_user_id=$2 and request_type=$3 and status not in ('COMPLETED','REJECTED') order by created_at desc limit 1`,[s.organizationId,s.id,requestType]);
      if(existing.rowCount)throw new HttpException({error:'privacy_request_already_open',request:existing.rows[0]},409);
      const r=await c.query(`insert into privacy.subject_request(tenant_id,subject_user_id,request_type,request_reason,requested_by) values($1,$2,$3,$4,$2) returning id,request_type,status,created_at`,[s.organizationId,s.id,requestType,text(body?.reason)||null]);
      await c.query(`insert into privacy.operation_event(tenant_id,subject_user_id,request_id,action,actor_id,metadata) values($1,$2,$3,'REQUEST_CREATED',$2,$4::jsonb)`,[s.organizationId,s.id,r.rows[0].id,JSON.stringify({requestType})]);
      return r.rows[0];
    });
  }

  @Get('requests')
  async requests(@Req() req:any,@Query('subjectUserId') subjectUserId?:string){
    const s=await this.session(req);const admin=s.roles?.includes('admin');if(subjectUserId&&!admin)throw new HttpException('forbidden',403);const subject=subjectUserId?uuidish(subjectUserId):String(s.id);
    return tenantTx(pool,s.organizationId,async c=>(await c.query(`select id,subject_user_id,request_type,status,request_reason,verified_at,decided_at,completed_at,rejection_reason,result_manifest,created_at,updated_at from privacy.subject_request where tenant_id=$1 and subject_user_id=$2 order by created_at desc`,[s.organizationId,subject])).rows);
  }

  @Get('me/export')
  async exportMe(@Req() req:any){
    const s=await this.session(req);
    return tenantTx(pool,s.organizationId,async c=>{
      const profile=(await c.query(`select id,email,display_name,privacy_status,anonymized_at,created_at from iam.user_profile where id=$1`,[s.id])).rows[0]||null;
      const memberships=(await c.query(`select m.organization_id,m.role,m.created_at,o.name,o.kind,o.status from iam.membership m join iam.organization o on o.id=m.organization_id where m.user_id=$1 and m.organization_id=$2`,[s.id,s.organizationId])).rows;
      const events=(await c.query(`select id,action,metadata,created_at from privacy.operation_event where tenant_id=$1 and subject_user_id=$2 order by created_at desc limit 1000`,[s.organizationId,s.id])).rows;
      return{status:'EXPORTED',scope:'PLATFORM_IDENTITY_AND_PRIVACY_WORKFLOW',generatedAt:new Date().toISOString(),tenantId:s.organizationId,profile,memberships,privacyEvents:events,limitations:['Domain records without an explicit subject_user_id relationship are not inferred as personal data by this endpoint.','Identity-provider data is external to this database export and requires the configured IdP process.'],protectedClasses:['AUDIT_TRAIL','LEGAL_EVIDENCE','SOURCE_PROVENANCE']};
    });
  }

  @Post('requests/:id/verify')
  async verify(@Req() req:any,@Param('id') id:string,@Body() body:any){
    const s=await this.session(req,true);id=uuidish(id);const reason=text(body?.reason);if(!reason)throw new HttpException('reason obrigatório',400);
    return tenantTx(pool,s.organizationId,async c=>{
      const r=await c.query(`update privacy.subject_request set status='IDENTITY_VERIFIED',verified_at=now(),reviewed_by=$3,result_manifest=result_manifest||$4::jsonb where id=$1 and tenant_id=$2 and status='REQUESTED' returning id,request_type,status,verified_at`,[id,s.organizationId,s.id,JSON.stringify({verificationReason:reason})]);
      if(!r.rowCount)throw new HttpException('privacy_request_not_verifiable',409);
      await c.query(`insert into privacy.operation_event(tenant_id,subject_user_id,request_id,action,actor_id,metadata) select tenant_id,subject_user_id,id,'IDENTITY_VERIFIED',$2,$3::jsonb from privacy.subject_request where id=$1`,[id,s.id,JSON.stringify({reason})]);return r.rows[0];
    });
  }

  @Post('requests/:id/decision')
  async decision(@Req() req:any,@Param('id') id:string,@Body() body:any){
    const s=await this.session(req,true);id=uuidish(id);const approved=body?.approved===true,reason=text(body?.reason);if(!reason)throw new HttpException('reason obrigatório',400);
    return tenantTx(pool,s.organizationId,async c=>{
      const r=await c.query(`update privacy.subject_request set status=$3,decided_at=now(),reviewed_by=$4,rejection_reason=case when $3='REJECTED' then $5 else null end,result_manifest=result_manifest||$6::jsonb where id=$1 and tenant_id=$2 and status='IDENTITY_VERIFIED' returning id,subject_user_id,request_type,status,decided_at`,[id,s.organizationId,approved?'APPROVED':'REJECTED',s.id,approved?null:reason,JSON.stringify({decisionReason:reason})]);
      if(!r.rowCount)throw new HttpException('privacy_request_not_decidable',409);const row=r.rows[0];
      await c.query(`insert into privacy.operation_event(tenant_id,subject_user_id,request_id,action,actor_id,metadata) values($1,$2,$3,$4,$5,$6::jsonb)`,[s.organizationId,row.subject_user_id,id,approved?'REQUEST_APPROVED':'REQUEST_REJECTED',s.id,JSON.stringify({reason})]);return row;
    });
  }

  @Post('requests/:id/execute')
  async execute(@Req() req:any,@Param('id') id:string,@Body() body:any){
    const s=await this.session(req,true);id=uuidish(id);const executionReason=text(body?.reason);if(!executionReason)throw new HttpException('reason obrigatório',400);
    const outcome=await tenantTx(pool,s.organizationId,async c=>{
      const q=await c.query(`select id,subject_user_id,request_type,status from privacy.subject_request where id=$1 and tenant_id=$2 for update`,[id,s.organizationId]);if(!q.rowCount)throw new HttpException('privacy_request_not_found',404);const row=q.rows[0];
      if(row.status!=='APPROVED')throw new HttpException('privacy_request_must_be_approved',409);if(TERMINAL.has(row.status))throw new HttpException('privacy_request_terminal',409);
      if(!['ACCESS','PORTABILITY','ERASURE'].includes(row.request_type))throw new HttpException('privacy_request_requires_manual_domain_workflow',409);
      await c.query(`update privacy.subject_request set status='EXECUTING' where id=$1`,[id]);
      if(row.request_type==='ERASURE'){
        const hold=(await c.query(`select privacy.has_active_hold($1,$2,'IDENTITY') active`,[s.organizationId,row.subject_user_id])).rows[0]?.active;if(hold)throw new HttpException('privacy_erasure_blocked_by_legal_hold',409);
        const removed=(await c.query(`delete from iam.membership where organization_id=$1 and user_id=$2 returning id`,[s.organizationId,row.subject_user_id])).rowCount||0;
        const remaining=Number((await c.query(`select count(*)::int n from iam.membership where user_id=$1`,[row.subject_user_id])).rows[0]?.n||0);
        let identityAction='TENANT_MEMBERSHIP_REMOVED_PROFILE_RETAINED';
        if(remaining===0){await c.query(`update iam.user_profile set email=$2,display_name=null,privacy_status='ANONYMIZED',anonymized_at=now(),privacy_note=$3 where id=$1`,[row.subject_user_id,`deleted+${row.subject_user_id}@privacy.invalid`,executionReason]);identityAction='IDENTITY_ANONYMIZED';}
        const manifest={scope:'TENANT',membershipRowsRemoved:removed,remainingMemberships:remaining,identityAction,sessionRevocation:'PENDING_AFTER_COMMIT',preservedClasses:['AUDIT_TRAIL','LEGAL_EVIDENCE','SOURCE_PROVENANCE'],externalActionsRequired:['IDENTITY_PROVIDER_REVIEW']};
        await c.query(`update privacy.subject_request set status='COMPLETED',completed_at=now(),result_manifest=result_manifest||$2::jsonb where id=$1`,[id,JSON.stringify(manifest)]);
        await c.query(`insert into privacy.operation_event(tenant_id,subject_user_id,request_id,action,actor_id,metadata) values($1,$2,$3,'ERASURE_EXECUTED',$4,$5::jsonb)`,[s.organizationId,row.subject_user_id,id,s.id,JSON.stringify({...manifest,reason:executionReason})]);
        return{subjectUserId:String(row.subject_user_id),requestType:row.request_type,manifest};
      }
      const profile=(await c.query(`select id,email,display_name,privacy_status,anonymized_at,created_at from iam.user_profile where id=$1`,[row.subject_user_id])).rows[0]||null;
      const membership=(await c.query(`select organization_id,role,created_at from iam.membership where user_id=$1 and organization_id=$2`,[row.subject_user_id,s.organizationId])).rows;
      const manifest={scope:'PLATFORM_IDENTITY_AND_CURRENT_TENANT',profile,membership,protectedClasses:['AUDIT_TRAIL','LEGAL_EVIDENCE','SOURCE_PROVENANCE'],externalActionsRequired:['IDENTITY_PROVIDER_EXPORT_IF_APPLICABLE']};
      await c.query(`update privacy.subject_request set status='COMPLETED',completed_at=now(),result_manifest=result_manifest||$2::jsonb where id=$1`,[id,JSON.stringify(manifest)]);
      await c.query(`insert into privacy.operation_event(tenant_id,subject_user_id,request_id,action,actor_id,metadata) values($1,$2,$3,'EXPORT_EXECUTED',$4,$5::jsonb)`,[s.organizationId,row.subject_user_id,id,s.id,JSON.stringify({reason:executionReason,scope:manifest.scope})]);
      return{subjectUserId:String(row.subject_user_id),requestType:row.request_type,manifest};
    });
    const sessionsRevoked=outcome.requestType==='ERASURE'?await this.auth.logoutUser(outcome.subjectUserId):0;
    return{status:'COMPLETED',requestId:id,requestType:outcome.requestType,...outcome.manifest,sessionsRevoked};
  }

  @Post('legal-holds')
  async createHold(@Req() req:any,@Body() body:any){
    const s=await this.session(req,true);const subject=body?.subjectUserId?uuidish(body.subjectUserId):null,category=text(body?.dataCategory||'ALL',80).toUpperCase(),reason=text(body?.reason),basis=text(body?.legalBasis);if(!reason||!basis)throw new HttpException('reason/legalBasis obrigatórios',400);
    return tenantTx(pool,s.organizationId,async c=>{const r=await c.query(`insert into privacy.legal_hold(tenant_id,subject_user_id,data_category,reason,legal_basis,ends_at,created_by) values($1,$2,$3,$4,$5,$6,$7) returning id,subject_user_id,data_category,reason,legal_basis,active,starts_at,ends_at`,[s.organizationId,subject,category,reason,basis,body?.endsAt||null,s.id]);await c.query(`insert into privacy.operation_event(tenant_id,subject_user_id,action,actor_id,metadata) values($1,$2,'LEGAL_HOLD_CREATED',$3,$4::jsonb)`,[s.organizationId,subject,s.id,JSON.stringify({holdId:r.rows[0].id,category,reason,basis})]);return r.rows[0];});
  }

  @Post('legal-holds/:id/release')
  async releaseHold(@Req() req:any,@Param('id') id:string,@Body() body:any){
    const s=await this.session(req,true);id=uuidish(id);const reason=text(body?.reason);if(!reason)throw new HttpException('reason obrigatório',400);
    return tenantTx(pool,s.organizationId,async c=>{const r=await c.query(`update privacy.legal_hold set active=false,released_by=$3,released_at=now(),release_reason=$4 where id=$1 and tenant_id=$2 and active=true returning id,subject_user_id,data_category,active,released_at`,[id,s.organizationId,s.id,reason]);if(!r.rowCount)throw new HttpException('legal_hold_not_releasable',409);await c.query(`insert into privacy.operation_event(tenant_id,subject_user_id,action,actor_id,metadata) values($1,$2,'LEGAL_HOLD_RELEASED',$3,$4::jsonb)`,[s.organizationId,r.rows[0].subject_user_id,s.id,JSON.stringify({holdId:id,reason})]);return r.rows[0];});
  }

  @Get('legal-holds')
  async holds(@Req() req:any,@Query('active') active?:string){const s=await this.session(req,true);return tenantTx(pool,s.organizationId,async c=>(await c.query(`select id,subject_user_id,data_category,reason,legal_basis,active,starts_at,ends_at,released_at,release_reason,created_at from privacy.legal_hold where tenant_id=$1 and ($2::boolean is null or active=$2::boolean) order by created_at desc`,[s.organizationId,active==null?null:active==='true'])).rows);}

  @Put('retention-policies/:category')
  async retention(@Req() req:any,@Param('category') rawCategory:string,@Body() body:any){
    const s=await this.session(req,true);const category=text(rawCategory,80).toUpperCase();const days=Number(body?.retentionDays),action=text(body?.expiryAction,24).toUpperCase(),basis=text(body?.legalBasis),owner=text(body?.owner,120);if(!category||!Number.isInteger(days)||days<0||!['RETAIN','ANONYMIZE','DELETE'].includes(action)||!basis||!owner)throw new HttpException('retention policy inválida',400);
    const protectedClass=PROTECTED_CATEGORIES.has(category);if(protectedClass&&(action!=='RETAIN'||body?.automaticExecution===true))throw new HttpException('protected_retention_class_cannot_be_destructive_or_automatic',409);
    return tenantTx(pool,s.organizationId,async c=>{const r=await c.query(`insert into privacy.retention_policy(tenant_id,data_category,retention_days,expiry_action,legal_basis,automatic_execution,protected_class,owner,notes) values($1,$2,$3,$4,$5,$6,$7,$8,$9) on conflict(tenant_id,data_category) do update set retention_days=excluded.retention_days,expiry_action=excluded.expiry_action,legal_basis=excluded.legal_basis,automatic_execution=excluded.automatic_execution,protected_class=excluded.protected_class,owner=excluded.owner,notes=excluded.notes,updated_at=now() returning *`,[s.organizationId,category,days,action,basis,body?.automaticExecution===true,protectedClass,owner,text(body?.notes)||null]);await c.query(`insert into privacy.operation_event(tenant_id,action,actor_id,metadata) values($1,'RETENTION_POLICY_UPDATED',$2,$3::jsonb)`,[s.organizationId,s.id,JSON.stringify({category,days,action,protectedClass})]);return r.rows[0];});
  }

  @Get('retention-policies')
  async retentionPolicies(@Req() req:any){const s=await this.session(req,true);return tenantTx(pool,s.organizationId,async c=>(await c.query(`select data_category,retention_days,expiry_action,legal_basis,automatic_execution,protected_class,owner,notes,updated_at from privacy.retention_policy where tenant_id=$1 order by data_category`,[s.organizationId])).rows);}
}
