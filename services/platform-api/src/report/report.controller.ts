import {Body,Controller,Get,HttpException,Param,Post,Req} from '@nestjs/common';
import {createHash,randomBytes} from 'crypto';
import {Pool} from 'pg';
import {AuthService} from '../auth.service';
import {tenantTx} from '../common/tenant-db';
import {withIdempotency} from '../common/idempotency';
import {enqueueOutbox} from '../common/outbox';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});
const TERMINAL_ANALYSIS_STATUSES=new Set(['COMPLETED','NEEDS_REVIEW','INSUFFICIENT_DATA']);

function reportBaseDate(value:any){
  if(value==null||value==='')return null;
  const v=String(value);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(v))throw new HttpException('baseDate deve estar em YYYY-MM-DD',400);
  return v;
}

@Controller('api/v1/reports')
export class ReportController{
  constructor(private readonly auth:AuthService){}
  private async session(req:any){const s=await this.auth.get(req.cookies?.ld_session);if(!s)throw new HttpException('unauthorized',401);const modules=Array.isArray(s.entitlements?.modules)?s.entitlements.modules:[];if(!s.roles?.includes('admin')&&!modules.includes('relatorios'))throw new HttpException('module_not_entitled',403);return s;}

  @Post()
  async requestReport(@Req() req:any,@Body() body:any){
    const s=await this.session(req);
    const subjectType=String(body?.subjectType||'').trim().toLowerCase();
    const subjectId=String(body?.subjectId||'').trim();
    const templateCode=String(body?.templateCode||'PROPERTY360_360').trim();
    const kind=String(body?.kind||'PROPERTY360').trim().toUpperCase();
    const requestedBaseDate=reportBaseDate(body?.baseDate);
    if(!['analysis','property'].includes(subjectType)||!subjectId)throw new HttpException('subjectType analysis/property e subjectId são obrigatórios',400);
    const key=String(req.headers?.['idempotency-key']||'').trim()||undefined;
    const idem=await withIdempotency(pool,s.organizationId,'report.request',key,async c=>{
      const template=await c.query(`select code,version,subject_types,status from report.template where code=$1`,[templateCode]);
      if(!template.rowCount||template.rows[0].status!=='ACTIVE')throw new HttpException('report_template_not_active',409);
      const accepted:string[]=Array.isArray(template.rows[0].subject_types)?template.rows[0].subject_types.map(String):[];
      if(!accepted.includes(subjectType))throw new HttpException('report_template_subject_not_supported',409);

      let baseDate=requestedBaseDate;
      let inputSnapshot:any={};
      if(subjectType==='analysis'){
        const subject=await c.query(`select id,base_date,status,input_snapshot from analysis.run where id=$1::uuid and tenant_id=$2`,[subjectId,s.organizationId]);
        if(!subject.rowCount)throw new HttpException('analysis_not_found',404);
        const analysisStatus=String(subject.rows[0].status||'').toUpperCase();
        if(!TERMINAL_ANALYSIS_STATUSES.has(analysisStatus))throw new HttpException('analysis_not_reportable',409);
        baseDate=baseDate||String(subject.rows[0].base_date);
        inputSnapshot={analysisRunId:subjectId,analysisStatus:subject.rows[0].status,analysisInputSnapshot:subject.rows[0].input_snapshot||{}};
      }else{
        const subject=await c.query(`select id,municipality_ibge,status,attributes from property360.property where id=$1::uuid and tenant_id=$2`,[subjectId,s.organizationId]);
        if(!subject.rowCount)throw new HttpException('property_not_found',404);
        baseDate=baseDate||new Date().toISOString().slice(0,10);
        inputSnapshot={propertyId:subjectId,municipalityIbge:subject.rows[0].municipality_ibge||null,propertyStatus:subject.rows[0].status,propertyAttributes:subject.rows[0].attributes||{}};
      }

      const run=await c.query(`insert into report.report_run(tenant_id,kind,subject_type,subject_id,base_date,status,input_snapshot,template_code,template_version,metadata)
        values($1,$2,$3,$4,$5::date,'QUEUED',$6::jsonb,$7,$8,$9::jsonb)
        returning id,kind,subject_type,subject_id,base_date,status,template_code,template_version,created_at`,
        [s.organizationId,kind,subjectType,subjectId,baseDate,JSON.stringify(inputSnapshot),templateCode,template.rows[0].version,JSON.stringify({requestedBy:s.email||s.id||null,requestContract:'report.request.v20'})]);
      const out=run.rows[0];
      await enqueueOutbox(c,'report.requested',{reportRunId:out.id,kind:out.kind,subjectType:out.subject_type,subjectId:out.subject_id,baseDate:out.base_date,templateCode:out.template_code,templateVersion:out.template_version},{tenantId:s.organizationId,aggregateType:'report.report_run',aggregateId:out.id,dedupeKey:`report.requested:${out.id}`});
      return out;
    });
    return{...idem.value,idempotency:{replayed:idem.replayed,key:key||null,contract:'report.request'}};
  }

  @Get(':id/status')
  async status(@Req() req:any,@Param('id') id:string){const s=await this.session(req);return tenantTx(pool,s.organizationId,async c=>{const r=await c.query(`select id,status,kind,subject_type,subject_id,base_date,template_code,template_version,renderer_version,artifact_key,sha256,frozen_at,created_at,completed_at,metadata from report.report_run where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!r.rowCount)throw new HttpException('report_not_found',404);return r.rows[0];});}

  @Get(':id/manifest')
  async manifest(@Req() req:any,@Param('id') id:string){const s=await this.session(req);return tenantTx(pool,s.organizationId,async c=>{const run=await c.query(`select id,kind,subject_type,subject_id,base_date,status,template_code,template_version,renderer_version,confidence_summary,metadata,artifact_key,sha256,frozen_at,created_at,completed_at from report.report_run where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!run.rowCount)throw new HttpException('report_not_found',404);const [snapshot,sections,evidence,artifacts,shares]=await Promise.all([c.query(`select schema_version,payload,sha256,created_at from report.snapshot where report_run_id=$1 and tenant_id=$2`,[id,s.organizationId]),c.query(`select section_code,ordinal,title,status,summary,payload,created_at from report.section where report_run_id=$1 and tenant_id=$2 order by ordinal`,[id,s.organizationId]),c.query(`select id,section_code,evidence_type,source_code,source_snapshot_id,source_document_version_id,source_locator,url,sha256,confidence_status,payload,created_at from report.evidence where report_run_id=$1 and tenant_id=$2 order by section_code,created_at`,[id,s.organizationId]),c.query(`select id,object_key,content_type,size_bytes,sha256,created_at from report.artifact where report_run_id=$1 and tenant_id=$2 order by created_at`,[id,s.organizationId]),c.query(`select id,audience,expires_at,revoked_at,created_by,created_at from report.share_link where report_run_id=$1 and tenant_id=$2 order by created_at desc`,[id,s.organizationId])]);return{run:run.rows[0],snapshot:snapshot.rows[0]||null,sections:sections.rows,evidence:evidence.rows,artifacts:artifacts.rows,shares:shares.rows};});}

  @Get(':id/sections')
  async sections(@Req() req:any,@Param('id') id:string){const s=await this.session(req);return tenantTx(pool,s.organizationId,async c=>{const own=await c.query(`select id from report.report_run where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!own.rowCount)throw new HttpException('report_not_found',404);return{items:(await c.query(`select section_code,ordinal,title,status,summary,payload from report.section where report_run_id=$1 and tenant_id=$2 order by ordinal`,[id,s.organizationId])).rows};});}

  @Post(':id/share')
  async share(@Req() req:any,@Param('id') id:string,@Body() body:any){const s=await this.session(req);const hours=Math.max(1,Math.min(Number(body?.expiresInHours||72),24*30));const token=randomBytes(32).toString('base64url');const hash=createHash('sha256').update(token).digest('hex');return tenantTx(pool,s.organizationId,async c=>{const own=await c.query(`select id,status from report.report_run where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!own.rowCount)throw new HttpException('report_not_found',404);if(own.rows[0].status!=='COMPLETED')throw new HttpException('report_not_completed',409);const r=await c.query(`insert into report.share_link(tenant_id,report_run_id,token_hash,audience,expires_at,created_by) values($1,$2,$3,$4,now()+($5||' hours')::interval,$6) returning id,audience,expires_at,created_at`,[s.organizationId,id,hash,String(body?.audience||'CLIENT'),String(hours),s.email||s.id]);return{...r.rows[0],token,warning:'O token é exibido uma única vez. A resolução pública/download assinado será habilitada somente após o gate de segurança específico.'};});}

  @Post(':id/share/:shareId/revoke')
  async revoke(@Req() req:any,@Param('id') id:string,@Param('shareId') shareId:string){const s=await this.session(req);return tenantTx(pool,s.organizationId,async c=>{const r=await c.query(`update report.share_link set revoked_at=coalesce(revoked_at,now()) where id=$1 and report_run_id=$2 and tenant_id=$3 returning id,revoked_at`,[shareId,id,s.organizationId]);if(!r.rowCount)throw new HttpException('share_link_not_found',404);return r.rows[0];});}
}
