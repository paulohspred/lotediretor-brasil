import {Body,Controller,Get,HttpException,Param,Post,Query,Req} from '@nestjs/common';
import {createHash} from 'crypto';
import {Pool} from 'pg';
import {AuthService} from '../auth.service';
import {tenantTx} from '../common/tenant-db';
import {withIdempotency} from '../common/idempotency';
import {enqueueOutbox} from '../common/outbox';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});
const SENSITIVE=/cpf|cnpj|titular|propriet|owner|autuado|email|telefone|phone|documento_pessoal|nome_pessoa/i;

function clean(value:any):any{
  if(Array.isArray(value))return value.map(clean);
  if(!value||typeof value!=='object')return value;
  const out:any={};for(const [k,v] of Object.entries(value)){out[k]=SENSITIVE.test(k)?'[RESTRICTED]':clean(v)}return out;
}
function norm(v:any){return String(v??'').trim().toUpperCase().replace(/[^A-Z0-9]/g,'');}
function hashState(v:any){return createHash('sha256').update(JSON.stringify(v)).digest('hex');}
function radius(v?:string){const n=Number(v??0);if(!Number.isFinite(n)||n<0||n>100000)throw new HttpException('radiusM deve estar entre 0 e 100000',400);return n;}

@Controller('api/v1/rural')
export class RuralController{
  constructor(private readonly auth:AuthService){}
  private async session(req:any){const s=await this.auth.get(req.cookies?.ld_session);if(!s?.organizationId)throw new HttpException('unauthorized',401);const modules=Array.isArray(s.entitlements?.modules)?s.entitlements.modules:[];if(!s.roles?.includes('admin')&&!modules.includes('re-rural'))throw new HttpException('module_not_entitled',403);return s;}
  private async admin(req:any){const s=await this.session(req);if(!s.roles?.includes('admin'))throw new HttpException('forbidden',403);return s;}

  @Get('search')
  async search(@Req() req:any,@Query('q') q='',@Query('municipality') municipality?:string,@Query('registryType') registryType?:string,@Query('baseDate') baseDateRaw?:string,@Query('lat') latRaw?:string,@Query('lon') lonRaw?:string,@Query('radiusM') radiusRaw?:string){
    const s=await this.session(req);const term=q.trim();if(term&&term.length<2)throw new HttpException('q deve ter ao menos 2 caracteres',400);
    const at=baseDateRaw||new Date().toISOString().slice(0,10);if(!/^\d{4}-\d{2}-\d{2}$/.test(at))throw new HttpException('baseDate deve estar em YYYY-MM-DD',400);const lat=latRaw==null?null:Number(latRaw),lon=lonRaw==null?null:Number(lonRaw),r=radius(radiusRaw);if((lat==null)!=(lon==null))throw new HttpException('lat e lon devem ser informados juntos',400);
    if(lat!==null&&(!Number.isFinite(lat)||lat < -90||lat > 90||lon===null||!Number.isFinite(lon)||lon < -180||lon > 180))throw new HttpException('coordenada inválida',400);
    return tenantTx(pool,s.organizationId,async c=>{
      const records=await c.query(`select rr.id record_id,rr.registry_type,rr.official_identifier,rr.attributes,rr.valid_from,rr.valid_to,
        a.id asset_id,a.name asset_name,a.municipality_ibge,s.id source_snapshot_id,s.sha256 source_sha256,s.source_date,s.validation_status,s.status snapshot_status,sr.code source_code,sr.authority,
        case when rr.geom is null then null else st_asgeojson(rr.geom)::jsonb end geometry
        from rural.registry_record rr join rural.asset a on a.id=rr.asset_id left join source.snapshot s on s.id=rr.source_snapshot_id left join source.registry sr on sr.id=s.source_id
        where (a.tenant_id=$1 or a.tenant_id is null) and ($2::text is null or a.municipality_ibge=$2) and ($3::text is null or rr.registry_type=$3)
          and (rr.valid_from is null or rr.valid_from <= $8::timestamptz) and (rr.valid_to is null or rr.valid_to > $8::timestamptz)
          and ($4::text='' or coalesce(rr.official_identifier,'') ilike '%'||$4||'%' or rr.attributes::text ilike '%'||$4||'%')
          and ($5::double precision is null or rr.geom is not null and st_dwithin(rr.geom::geography,st_setsrid(st_makepoint($6,$5),4326)::geography,$7))
        order by rr.valid_from desc nulls last,rr.id limit 100`,[s.organizationId,municipality||null,registryType||null,term,lat,lon,r||100000,`${at}T12:00:00Z`]);
      const features=await c.query(`select lf.id feature_id,lc.code registry_type,lf.official_identifier,lf.attributes,lf.valid_from,lf.valid_to,lf.source_snapshot_id,s.sha256 source_sha256,s.source_date,s.validation_status,s.status snapshot_status,lc.authority,
        st_asgeojson(lf.geom)::jsonb geometry
        from rural.layer_feature lf join rural.layer_catalog lc on lc.code=lf.layer_code join source.snapshot s on s.id=lf.source_snapshot_id
        where lf.source_snapshot_id in (select p.snapshot_id from source.publication p where p.status='ACTIVE') and ($2::text is null or exists(select 1 from geo.municipality_boundary mb where mb.municipality_ibge=$2 and st_intersects(mb.geom,lf.geom))) and (lf.valid_from is null or lf.valid_from <= $8::timestamptz) and (lf.valid_to is null or lf.valid_to > $8::timestamptz) and ($3::text is null or lc.code=$3) and ($4::text='' or coalesce(lf.official_identifier,'') ilike '%'||$4||'%' or lf.attributes::text ilike '%'||$4||'%')
          and ($5::double precision is null or st_dwithin(lf.geom::geography,st_setsrid(st_makepoint($6,$5),4326)::geography,$7))
        order by lf.recorded_at desc limit 100`,[s.organizationId,municipality||null,registryType||null,term,lat,lon,r||100000,`${at}T12:00:00Z`]);
      return{query:{q:term,municipality:municipality||null,registryType:registryType||null,baseDate:at,point:lat==null?null:{lat,lon,radiusM:r||100000}},items:[...records.rows.map((x:any)=>({...x,kind:'REGISTRY_RECORD',attributes:clean(x.attributes),sensitiveFields:'REDACTED_BY_DEFAULT'})),...features.rows.map((x:any)=>({...x,kind:'OFFICIAL_LAYER_FEATURE',attributes:clean(x.attributes),sensitiveFields:'REDACTED_BY_DEFAULT'}))],limitations:['Busca não transforma CAR/SNCR/SIGEF/CIB em prova de domínio.','Campos pessoais/sensíveis são removidos da resposta padrão.']};
    });
  }

  @Post('assets/:id/registry-records/:recordId/identifiers')
  async addIdentifier(@Req() req:any,@Param('id') id:string,@Param('recordId') recordId:string,@Body() body:any){
    const s=await this.session(req);const type=String(body?.type||'').trim().toUpperCase(),value=String(body?.value||'').trim();if(['CPF','CNPJ'].includes(type))throw new HttpException('CPF/CNPJ bruto não pode ser salvo como registry_identifier; use conector autorizado com tokenização',400);if(!type||!value)throw new HttpException('type e value são obrigatórios',400);
    return tenantTx(pool,s.organizationId,async c=>{const own=await c.query(`select rr.id from rural.registry_record rr join rural.asset a on a.id=rr.asset_id where rr.id=$1 and a.id=$2 and a.tenant_id=$3`,[recordId,id,s.organizationId]);if(!own.rowCount)throw new HttpException('tenant_owned_registry_record_required',409);const r=await c.query(`insert into rural.registry_identifier(asset_id,registry_record_id,identifier_type,identifier_value,normalized_value,source_snapshot_id,status,valid_from,valid_to) select $1,$2,$3,$4,$5,source_snapshot_id,$6,$7,$8 from rural.registry_record where id=$2 returning id,identifier_type,identifier_value,status,created_at`,[id,recordId,type,value,norm(value),String(body?.status||'OBSERVED'),body?.validFrom||null,body?.validTo||null]);return r.rows[0];});
  }

  @Post('assets/:id/identity-graph/rebuild')
  async rebuildIdentity(@Req() req:any,@Param('id') id:string){
    const s=await this.session(req);const key=String(req.headers?.['idempotency-key']||'').trim()||undefined;
    const idem=await withIdempotency(pool,s.organizationId,`rural.identity.rebuild:${id}`,key,async c=>{const own=await c.query(`select id from rural.asset where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!own.rowCount)throw new HttpException('tenant_owned_asset_required',409);
      const rows=(await c.query(`select rr.id,rr.registry_type,rr.official_identifier,rr.attributes,case when rr.geom is null then null else st_area(rr.geom::geography) end area_m2,rr.geom,array_remove(array_agg(ri.normalized_value),null) identifiers from rural.registry_record rr left join rural.registry_identifier ri on ri.registry_record_id=rr.id where rr.asset_id=$1 group by rr.id`,[id])).rows;
      await c.query(`delete from rural.identity_link where asset_id=$1 and status='CANDIDATE'`,[id]);let created=0;
      for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++){const a=rows[i],b=rows[j],reasons:any[]=[];let confidence=0;const idsA=new Set((a.identifiers||[]).filter(Boolean)),idsB=new Set((b.identifiers||[]).filter(Boolean));const common=[...idsA].filter(x=>idsB.has(x));if(common.length){confidence=.95;reasons.push({code:'SHARED_NORMALIZED_IDENTIFIER',values:common});}
        if(a.geom&&b.geom){const g=await c.query(`select st_area(st_intersection($1::geometry,$2::geometry)::geography) inter,least(st_area($1::geometry::geography),st_area($2::geometry::geography)) denom`,[a.geom,b.geom]);const ratio=Number(g.rows[0]?.denom)>0?Number(g.rows[0]?.inter)/Number(g.rows[0]?.denom):0;if(ratio>.9){confidence=Math.max(confidence,.8);reasons.push({code:'GEOMETRY_OVERLAP',ratio});}else if(ratio>.5){confidence=Math.max(confidence,.6);reasons.push({code:'PARTIAL_GEOMETRY_OVERLAP',ratio});}}
        if(confidence>0){await c.query(`insert into rural.identity_link(asset_id,left_record_id,right_record_id,relationship,confidence,status,reasons) values($1,$2,$3,'SAME_PHYSICAL_AREA_CANDIDATE',$4,'CANDIDATE',$5::jsonb)`,[id,a.id,b.id,confidence,JSON.stringify(reasons)]);created++;}}
      return{assetId:id,registryRecords:rows.length,candidateLinksCreated:created,rule:'Nenhum vínculo automático prova domínio/titularidade; todos permanecem CANDIDATE até revisão.'};});
    return{...idem.value,idempotency:{replayed:idem.replayed,key:key||null}};
  }

  @Get('assets/:id/identity-graph')
  async identityGraph(@Req() req:any,@Param('id') id:string){
    const s=await this.session(req);return tenantTx(pool,s.organizationId,async c=>{const asset=await c.query(`select id,name,municipality_ibge from rural.asset where id=$1 and (tenant_id=$2 or tenant_id is null)`,[id,s.organizationId]);if(!asset.rowCount)throw new HttpException('asset_not_found',404);const [records,links,ids]=await Promise.all([c.query(`select id,registry_type,official_identifier,source_snapshot_id,valid_from,valid_to from rural.registry_record where asset_id=$1 order by registry_type`,[id]),c.query(`select id,left_record_id,right_record_id,relationship,confidence,status,reasons,reviewed_by,reviewed_at from rural.identity_link where asset_id=$1 order by confidence desc`,[id]),c.query(`select registry_record_id,identifier_type,case when identifier_type in ('CPF','CNPJ') then '[RESTRICTED]' else identifier_value end identifier_value,status from rural.registry_identifier where asset_id=$1 order by identifier_type`,[id])]);return{asset:asset.rows[0],nodes:records.rows.map((x:any)=>({...x,identifiers:ids.rows.filter((i:any)=>i.registry_record_id===x.id)})),links:links.rows,semanticRule:'Cada registro conserva sua natureza jurídica. Links representam convergência/divergência e não fusão de identidade.'};});
  }

  @Post('assets/:id/monitors/:monitorId/check')
  async checkMonitor(@Req() req:any,@Param('id') id:string,@Param('monitorId') monitorId:string){
    const s=await this.session(req);const key=String(req.headers?.['idempotency-key']||'').trim()||undefined;
    const idem=await withIdempotency(pool,s.organizationId,`rural.monitor.check:${monitorId}`,key,async c=>{const monitor=await c.query(`select m.id,m.monitor_type,m.configuration from rural.monitor m join rural.asset a on a.id=m.asset_id where m.id=$1 and m.asset_id=$2 and m.tenant_id=$3 and a.tenant_id=$3 and m.status='ACTIVE'`,[monitorId,id,s.organizationId]);if(!monitor.rowCount)throw new HttpException('active_monitor_not_found',404);
      const current=await c.query(`select code,official_identifier,source_snapshot_id,geometry_hash from (select lc.code,lf.official_identifier,lf.source_snapshot_id,encode(digest(st_asbinary(lf.geom),'sha256'),'hex') geometry_hash,lf.id::text sort_id from rural.asset a join rural.layer_feature lf on a.geom is not null and st_intersects(a.geom,lf.geom) join rural.layer_catalog lc on lc.code=lf.layer_code where a.id=$1 and lf.source_snapshot_id in (select p.snapshot_id from source.publication p where p.status='ACTIVE') union all select rr.registry_type code,rr.official_identifier,rr.source_snapshot_id,case when rr.geom is null then null else encode(digest(st_asbinary(rr.geom),'sha256'),'hex') end geometry_hash,rr.id::text sort_id from rural.registry_record rr where rr.asset_id=$1 and (rr.valid_from is null or rr.valid_from <= now()) and (rr.valid_to is null or rr.valid_to > now())) x order by code,official_identifier nulls last,sort_id`,[id]);
      const state=current.rows.map((x:any)=>({source:x.code,id:x.official_identifier||null,snapshotId:x.source_snapshot_id,geometryHash:x.geometry_hash}));const stateHash=hashState(state);const previous=await c.query(`select id,state_hash,state,source_snapshot_ids,checked_at from rural.monitor_checkpoint where monitor_id=$1 and tenant_id=$2 order by checked_at desc limit 1`,[monitorId,s.organizationId]);const snapshotIds=[...new Set(state.map((x:any)=>x.snapshotId).filter(Boolean))];const cp=await c.query(`insert into rural.monitor_checkpoint(tenant_id,monitor_id,state_hash,state,source_snapshot_ids) values($1,$2,$3,$4::jsonb,$5::uuid[]) on conflict(monitor_id,state_hash) do update set checked_at=excluded.checked_at,state=excluded.state,source_snapshot_ids=excluded.source_snapshot_ids returning id,checked_at`,[s.organizationId,monitorId,stateHash,JSON.stringify(state),snapshotIds]);const changed=previous.rowCount>0&&previous.rows[0].state_hash!==stateHash;
      if(changed){await c.query(`insert into rural.monitor_event(tenant_id,monitor_id,event_type,status,before_snapshot_id,after_snapshot_id,change_summary) values($1,$2,'SOURCE_INTERSECTION_CHANGED','NEW',$3,$4,$5::jsonb)`,[s.organizationId,monitorId,previous.rows[0].source_snapshot_ids?.[0]||null,snapshotIds[0]||null,JSON.stringify({previousHash:previous.rows[0].state_hash,currentHash:stateHash,previousCount:(previous.rows[0].state||[]).length,currentCount:state.length})]);await c.query(`update rural.monitor set last_checked_at=now(),last_change_at=now() where id=$1`,[monitorId]);}else await c.query(`update rural.monitor set last_checked_at=now() where id=$1`,[monitorId]);
      return{monitorId,baseline:!previous.rowCount,changed,stateHash,featureCount:state.length,checkpointId:cp.rows[0].id};});
    return{...idem.value,idempotency:{replayed:idem.replayed,key:key||null}};
  }

  @Post('assets/:id/exports')
  async export(@Req() req:any,@Param('id') id:string,@Body() body:any){const s=await this.session(req);const format=String(body?.format||'KML').toUpperCase();if(!['KML','KMZ'].includes(format))throw new HttpException('format deve ser KML ou KMZ',400);const key=String(req.headers?.['idempotency-key']||'').trim()||undefined;const idem=await withIdempotency(pool,s.organizationId,`rural.export:${id}:${format}`,key,async c=>{const own=await c.query(`select id from rural.asset where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!own.rowCount)throw new HttpException('tenant_owned_asset_required',409);const r=await c.query(`insert into rural.export_job(tenant_id,asset_id,format,status,created_by,metadata) values($1,$2,$3,'QUEUED',$4,$5::jsonb) returning id,asset_id,format,status,created_at`,[s.organizationId,id,format,s.email||s.id,JSON.stringify({includeRegistryLayers:body?.includeRegistryLayers!==false})]);await enqueueOutbox(c,'rural.export.queued',{exportJobId:r.rows[0].id,assetId:id,format},{tenantId:s.organizationId,aggregateType:'rural.export_job',aggregateId:r.rows[0].id,dedupeKey:`rural.export.queued:${r.rows[0].id}`});return r.rows[0];});return{...idem.value,idempotency:{replayed:idem.replayed,key:key||null}};}

  @Get('exports/:id')
  async exportStatus(@Req() req:any,@Param('id') id:string){const s=await this.session(req);return tenantTx(pool,s.organizationId,async c=>{const r=await c.query(`select id,asset_id,format,status,object_key,sha256,size_bytes,metadata,created_at,completed_at from rural.export_job where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!r.rowCount)throw new HttpException('export_not_found',404);return r.rows[0];});}

  @Post('assets/:id/report')
  async ruralReport(@Req() req:any,@Param('id') id:string,@Body() body:any){const s=await this.session(req);const key=String(req.headers?.['idempotency-key']||'').trim()||undefined;const idem=await withIdempotency(pool,s.organizationId,'rural360.report',key,async c=>{await c.query(`select set_config('app.tenant_id',$1,true)`,[s.organizationId]);const asset=await c.query(`select id,municipality_ibge from rural.asset where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!asset.rowCount)throw new HttpException('tenant_owned_asset_required',409);const tpl=await c.query(`select code,version from report.template where code='RURAL360_360' and status='ACTIVE'`);if(!tpl.rowCount)throw new HttpException('rural_report_template_not_found',500);const baseDate=String(body?.baseDate||new Date().toISOString().slice(0,10));const r=await c.query(`insert into report.report_run(tenant_id,kind,subject_type,subject_id,base_date,status,input_snapshot,template_code,template_version,metadata) values($1,'RURAL360','rural_asset',$2,$3,'QUEUED',$4::jsonb,$5,$6,$7::jsonb) returning id,status,template_code,template_version,created_at`,[s.organizationId,id,baseDate,JSON.stringify({assetId:id,municipalityIbge:asset.rows[0].municipality_ibge}),tpl.rows[0].code,tpl.rows[0].version,JSON.stringify({requestedBy:s.email||s.id,schemaVersion:'rural-360-v1'})]);await enqueueOutbox(c,'report.queued',{reportRunId:r.rows[0].id,kind:'RURAL360',subjectType:'rural_asset',subjectId:id,baseDate},{tenantId:s.organizationId,aggregateType:'report.report_run',aggregateId:r.rows[0].id,dedupeKey:`report.queued:${r.rows[0].id}`});return r.rows[0];});return{...idem.value,idempotency:{replayed:idem.replayed,key:key||null}};}

  @Post('identity-links/:linkId/review')
  async reviewLink(@Req() req:any,@Param('linkId') linkId:string,@Body() body:any){const s=await this.admin(req);const decision=String(body?.decision||'').toUpperCase();if(!['CONFIRMED','REJECTED'].includes(decision))throw new HttpException('decision deve ser CONFIRMED ou REJECTED',400);return tenantTx(pool,s.organizationId,async c=>{const r=await c.query(`update rural.identity_link il set status=$2,reviewed_by=$3,reviewed_at=now() from rural.asset a where il.id=$1 and a.id=il.asset_id and a.tenant_id=$4 returning il.id,il.relationship,il.confidence,il.status,il.reasons,il.reviewed_by,il.reviewed_at`,[linkId,decision,s.email||s.id,s.organizationId]);if(!r.rowCount)throw new HttpException('identity_link_not_found',404);return r.rows[0];});}
}
