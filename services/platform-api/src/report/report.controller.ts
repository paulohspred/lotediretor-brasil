import {Body,Controller,Get,HttpException,Param,Post,Req} from '@nestjs/common';
import {createHash,randomBytes} from 'crypto';
import {Pool} from 'pg';
import {AuthService} from '../auth.service';
import {tenantTx} from '../common/tenant-db';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});

@Controller('api/v1/reports')
export class ReportController{
  constructor(private readonly auth:AuthService){}
  private async session(req:any){const s=await this.auth.get(req.cookies?.ld_session);if(!s)throw new HttpException('unauthorized',401);const modules=Array.isArray(s.entitlements?.modules)?s.entitlements.modules:[];if(!s.roles?.includes('admin')&&!modules.includes('relatorios'))throw new HttpException('module_not_entitled',403);return s;}

  @Get(':id/manifest')
  async manifest(@Req() req:any,@Param('id') id:string){const s=await this.session(req);return tenantTx(pool,s.organizationId,async c=>{const run=await c.query(`select id,kind,subject_type,subject_id,base_date,status,template_code,template_version,renderer_version,confidence_summary,metadata,artifact_key,sha256,frozen_at,created_at,completed_at from report.report_run where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!run.rowCount)throw new HttpException('report_not_found',404);const [snapshot,sections,evidence,artifacts,shares]=await Promise.all([c.query(`select schema_version,payload,sha256,created_at from report.snapshot where report_run_id=$1 and tenant_id=$2`,[id,s.organizationId]),c.query(`select section_code,ordinal,title,status,summary,payload,created_at from report.section where report_run_id=$1 and tenant_id=$2 order by ordinal`,[id,s.organizationId]),c.query(`select id,section_code,evidence_type,source_code,source_snapshot_id,source_document_version_id,source_locator,url,sha256,confidence_status,payload,created_at from report.evidence where report_run_id=$1 and tenant_id=$2 order by section_code,created_at`,[id,s.organizationId]),c.query(`select id,object_key,content_type,size_bytes,sha256,created_at from report.artifact where report_run_id=$1 and tenant_id=$2 order by created_at`,[id,s.organizationId]),c.query(`select id,audience,expires_at,revoked_at,created_by,created_at from report.share_link where report_run_id=$1 and tenant_id=$2 order by created_at desc`,[id,s.organizationId])]);return{run:run.rows[0],snapshot:snapshot.rows[0]||null,sections:sections.rows,evidence:evidence.rows,artifacts:artifacts.rows,shares:shares.rows};});}

  @Get(':id/sections')
  async sections(@Req() req:any,@Param('id') id:string){const s=await this.session(req);return tenantTx(pool,s.organizationId,async c=>{const own=await c.query(`select id from report.report_run where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!own.rowCount)throw new HttpException('report_not_found',404);return{items:(await c.query(`select section_code,ordinal,title,status,summary,payload from report.section where report_run_id=$1 and tenant_id=$2 order by ordinal`,[id,s.organizationId])).rows};});}

  @Post(':id/share')
  async share(@Req() req:any,@Param('id') id:string,@Body() body:any){const s=await this.session(req);const hours=Math.max(1,Math.min(Number(body?.expiresInHours||72),24*30));const token=randomBytes(32).toString('base64url');const hash=createHash('sha256').update(token).digest('hex');return tenantTx(pool,s.organizationId,async c=>{const own=await c.query(`select id,status from report.report_run where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!own.rowCount)throw new HttpException('report_not_found',404);if(own.rows[0].status!=='COMPLETED')throw new HttpException('report_not_completed',409);const r=await c.query(`insert into report.share_link(tenant_id,report_run_id,token_hash,audience,expires_at,created_by) values($1,$2,$3,$4,now()+($5||' hours')::interval,$6) returning id,audience,expires_at,created_at`,[s.organizationId,id,hash,String(body?.audience||'CLIENT'),String(hours),s.email||s.id]);return{...r.rows[0],token,warning:'O token é exibido uma única vez. A resolução pública/download assinado será habilitada somente após o gate de segurança específico.'};});}

  @Post(':id/share/:shareId/revoke')
  async revoke(@Req() req:any,@Param('id') id:string,@Param('shareId') shareId:string){const s=await this.session(req);return tenantTx(pool,s.organizationId,async c=>{const r=await c.query(`update report.share_link set revoked_at=coalesce(revoked_at,now()) where id=$1 and report_run_id=$2 and tenant_id=$3 returning id,revoked_at`,[shareId,id,s.organizationId]);if(!r.rowCount)throw new HttpException('share_link_not_found',404);return r.rows[0];});}
}
