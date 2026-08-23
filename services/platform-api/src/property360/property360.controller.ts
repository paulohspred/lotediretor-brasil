import {Body,Controller,Get,HttpException,Param,Post,Query,Req} from '@nestjs/common';
import {Pool} from 'pg';
import {AuthService} from '../auth.service';
import {tenantTx} from '../common/tenant-db';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});

@Controller('api/v1/property360')
export class Property360Controller{
  constructor(private readonly auth:AuthService){}
  private async session(req:any){const s=await this.auth.get(req.cookies?.ld_session);if(!s)throw new HttpException('unauthorized',401);const modules=Array.isArray(s.entitlements?.modules)?s.entitlements.modules:[];if(!s.roles?.includes('admin')&&!modules.includes('imovel360'))throw new HttpException('module_not_entitled',403);return s;}

  @Post('properties/from-analysis')
  async fromAnalysis(@Req() req:any,@Body() body:any){
    const s=await this.session(req);const runId=String(body?.analysisRunId||'');if(!runId)throw new HttpException('analysisRunId obrigatório',400);
    return tenantTx(pool,s.organizationId,async c=>{
      const run=await c.query(`select id,property_id,input_snapshot,base_date from analysis.run where id=$1 and tenant_id=$2`,[runId,s.organizationId]);if(!run.rowCount)throw new HttpException('analysis_not_found',404);
      if(run.rows[0].property_id){const existing=await c.query(`select id,name,address,municipality_ibge,status,tags,attributes,created_at,updated_at from property360.property where id=$1 and tenant_id=$2`,[run.rows[0].property_id,s.organizationId]);return{property:existing.rows[0],linkedAnalysisRunId:runId,reused:true};}
      const snap=run.rows[0].input_snapshot||{};const parcelId=String(snap.resolvedParcelId||'');if(!parcelId)throw new HttpException('analysis_without_resolved_parcel',409);
      const parcel=await c.query(`select id,municipality_ibge,geom,official_identifier from geo.parcel where id=$1 and (tenant_id is null or tenant_id=$2)`,[parcelId,s.organizationId]);if(!parcel.rowCount)throw new HttpException('parcel_not_found',404);
      const name=String(body?.name||`Imóvel ${parcel.rows[0].official_identifier||parcelId.slice(0,8)}`);const address=body?.address?String(body.address):null;const tags=Array.isArray(body?.tags)?body.tags.map(String):[];
      const p=await c.query(`insert into property360.property(tenant_id,name,address,municipality_ibge,geom,status,tags,attributes) values($1,$2,$3,$4,$5,'ACTIVE',$6,$7::jsonb) returning id,name,address,municipality_ibge,status,tags,attributes,created_at,updated_at`,[s.organizationId,name,address,parcel.rows[0].municipality_ibge,parcel.rows[0].geom,tags,JSON.stringify({sourceAnalysisRunId:runId,parcelId})]);
      await c.query(`update analysis.run set property_id=$1 where id=$2 and tenant_id=$3`,[p.rows[0].id,runId,s.organizationId]);
      return{property:p.rows[0],linkedAnalysisRunId:runId,reused:false};
    });
  }

  @Get('properties/:id/ficha')
  async ficha(@Req() req:any,@Param('id') id:string){
    const s=await this.session(req);
    return tenantTx(pool,s.organizationId,async c=>{
      const p=await c.query(`select id,name,address,municipality_ibge,status,tags,attributes,st_asgeojson(geom)::jsonb geometry,created_at,updated_at from property360.property where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!p.rowCount)throw new HttpException('property_not_found',404);
      const [analyses,avms,notes,diligences,reports,leads,developments]=await Promise.all([
        c.query(`select id,status,base_date,input_snapshot,created_at from analysis.run where property_id=$1 and tenant_id=$2 order by created_at desc limit 50`,[id,s.organizationId]),
        c.query(`select id,municipality_ibge,area_m2,model_version,status,estimate_cents,confidence,assumptions,created_at from property360.avm_run where property_id=$1 and tenant_id=$2 order by created_at desc limit 50`,[id,s.organizationId]),
        c.query(`select id,body,tags,created_by,created_at from property360.property_note where property_id=$1 and tenant_id=$2 order by created_at desc limit 100`,[id,s.organizationId]),
        c.query(`select id,title,description,status,priority,owner_user_id,due_at,completed_at,evidence,created_at,updated_at from property360.diligence where property_id=$1 and tenant_id=$2 order by created_at desc limit 100`,[id,s.organizationId]),
        c.query(`select rr.id,rr.kind,rr.subject_type,rr.subject_id,rr.base_date,rr.status,rr.template_code,rr.template_version,rr.renderer_version,rr.confidence_summary,rr.sha256,rr.created_at,rr.completed_at from report.report_run rr where rr.tenant_id=$2 and (rr.subject_type='property' and rr.subject_id=$1 or rr.subject_type='analysis' and rr.subject_id in (select id::text from analysis.run where property_id=$1 and tenant_id=$2)) order by rr.created_at desc limit 50`,[id,s.organizationId]),
        c.query(`select id,name,stage,score,owner_user_id,tags,notes,created_at,updated_at from crm.lead where property_id=$1 and tenant_id=$2 order by created_at desc limit 50`,[id,s.organizationId]),
        c.query(`select d.id,d.name,d.status,d.municipality_ibge,d.gross_land_area_m2,d.attributes,d.created_at from property360.development d join property360.development_parcel dp on dp.development_id=d.id join analysis.run ar on ar.property_id=$1 and ar.tenant_id=$2 join geo.parcel gp on gp.id=(ar.input_snapshot->>'resolvedParcelId')::uuid and gp.id=dp.parcel_id where d.tenant_id=$2 order by d.created_at desc limit 50`,[id,s.organizationId])
      ]);
      return{property:p.rows[0],analyses:analyses.rows,avmRuns:avms.rows,notes:notes.rows,diligences:diligences.rows,reports:reports.rows,crmLeads:leads.rows,developments:developments.rows};
    });
  }

  @Post('properties/:id/notes')
  async note(@Req() req:any,@Param('id') id:string,@Body() body:any){const s=await this.session(req);const text=String(body?.body||'').trim();if(!text)throw new HttpException('body obrigatório',400);return tenantTx(pool,s.organizationId,async c=>{const own=await c.query(`select id from property360.property where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!own.rowCount)throw new HttpException('property_not_found',404);const r=await c.query(`insert into property360.property_note(tenant_id,property_id,body,tags,created_by) values($1,$2,$3,$4,$5) returning id,body,tags,created_by,created_at`,[s.organizationId,id,text,Array.isArray(body?.tags)?body.tags.map(String):[],s.email||s.id]);return r.rows[0];});}

  @Get('properties/:id/notes')
  async notes(@Req() req:any,@Param('id') id:string){const s=await this.session(req);return tenantTx(pool,s.organizationId,async c=>({items:(await c.query(`select id,body,tags,created_by,created_at from property360.property_note where property_id=$1 and tenant_id=$2 order by created_at desc limit 200`,[id,s.organizationId])).rows}));}

  @Post('diligences')
  async diligence(@Req() req:any,@Body() body:any){const s=await this.session(req);const propertyId=body?.propertyId?String(body.propertyId):null;const developmentId=body?.developmentId?String(body.developmentId):null;if(!propertyId&&!developmentId)throw new HttpException('propertyId ou developmentId obrigatório',400);const title=String(body?.title||'').trim();if(!title)throw new HttpException('title obrigatório',400);return tenantTx(pool,s.organizationId,async c=>{if(propertyId){const own=await c.query(`select id from property360.property where id=$1 and tenant_id=$2`,[propertyId,s.organizationId]);if(!own.rowCount)throw new HttpException('property_not_found',404);}if(developmentId){const own=await c.query(`select id from property360.development where id=$1 and tenant_id=$2`,[developmentId,s.organizationId]);if(!own.rowCount)throw new HttpException('development_not_found',404);}const r=await c.query(`insert into property360.diligence(tenant_id,property_id,development_id,title,description,status,priority,owner_user_id,due_at,evidence) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb) returning *`,[s.organizationId,propertyId,developmentId,title,body?.description||null,String(body?.status||'OPEN'),String(body?.priority||'MEDIUM'),body?.ownerUserId||null,body?.dueAt||null,JSON.stringify(body?.evidence||{})]);return r.rows[0];});}

  @Get('diligences')
  async diligences(@Req() req:any,@Query('propertyId') propertyId?:string,@Query('status') status?:string){const s=await this.session(req);return tenantTx(pool,s.organizationId,async c=>({items:(await c.query(`select id,property_id,development_id,title,description,status,priority,owner_user_id,due_at,completed_at,evidence,created_at,updated_at from property360.diligence where tenant_id=$1 and ($2::uuid is null or property_id=$2::uuid) and ($3::text is null or status=$3) order by created_at desc limit 200`,[s.organizationId,propertyId||null,status||null])).rows}));}
}
