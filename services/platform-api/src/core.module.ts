import {Body,Controller,Get,HttpException,HttpStatus,Module,Param,Post,Query,Req,Res} from '@nestjs/common';
import {Pool,PoolClient} from 'pg';
import {createHash,randomUUID} from 'crypto';
import {S3Client,PutObjectCommand} from '@aws-sdk/client-s3';
import {AuthService} from './auth.service';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});
const s3=new S3Client({endpoint:process.env.S3_ENDPOINT||'http://minio:9000',region:process.env.S3_REGION||'us-east-1',forcePathStyle:true,credentials:{accessKeyId:process.env.S3_ACCESS_KEY||'lotediretor',secretAccessKey:process.env.S3_SECRET_KEY||'lotediretor-local-secret'}});
const S3_BUCKET=process.env.S3_BUCKET||'lotediretor';
import {PLATFORM_VERSION} from './version';
import {withIdempotency} from './common/idempotency';
import {enqueueOutbox} from './common/outbox';
import {decodeCursor,encodeCursor,pageLimit} from './common/cursor';
import {tenantQuery,tenantTx} from './common/tenant-db';
const VERSION=PLATFORM_VERSION;

function asNumber(value:unknown,name:string){const n=Number(value);if(!Number.isFinite(n))throw new HttpException(`${name} inválido`,400);return n}
function baseDate(value?:string){if(!value)return new Date().toISOString().slice(0,10);if(!/^\d{4}-\d{2}-\d{2}$/.test(value))throw new HttpException('baseDate deve estar em YYYY-MM-DD',400);return value}
async function tx<T>(fn:(c:PoolClient)=>Promise<T>){const c=await pool.connect();try{await c.query('BEGIN');const out=await fn(c);await c.query('COMMIT');return out}catch(e){await c.query('ROLLBACK');throw e}finally{c.release()}}

@Controller('api/v1')
class ApiController{
  constructor(private readonly auth:AuthService){}
  private async session(req:any){const s=await this.auth.get(req.cookies?.ld_session);if(!s)throw new HttpException('unauthorized',HttpStatus.UNAUTHORIZED);return s}
  private async admin(req:any){const s=await this.session(req);if(!s.roles?.includes('admin'))throw new HttpException('forbidden',HttpStatus.FORBIDDEN);return s}
  private async moduleSession(req:any,code:string){const s=await this.session(req);const modules=Array.isArray(s.entitlements?.modules)?s.entitlements.modules:[];if(!s.roles?.includes('admin')&&!modules.includes(code))throw new HttpException('module_not_entitled',HttpStatus.FORBIDDEN);return s}

  @Get('health') health(){return{ok:true,service:'platform-api',version:VERSION}}
  @Get('auth/start') start(@Query('returnTo') returnTo:string,@Res() res:any){const a=this.auth.start(returnTo);const secure=process.env.SESSION_COOKIE_SECURE==='true';res.setCookie('ld_oidc_state',a.state,{httpOnly:true,sameSite:'lax',secure,path:'/',maxAge:600});res.setCookie('ld_oidc_verifier',a.verifier,{httpOnly:true,sameSite:'lax',secure,path:'/',maxAge:600});res.setCookie('ld_return_to',a.returnTo,{httpOnly:true,sameSite:'lax',secure,path:'/',maxAge:600});return res.redirect(a.url)}
  @Get('auth/callback') async callback(@Query('code') code:string,@Query('state') state:string,@Req() req:any,@Res() res:any){if(!code||!state||state!==req.cookies?.ld_oidc_state)throw new HttpException('invalid oidc state',400);const out=await this.auth.callback(code,req.cookies?.ld_oidc_verifier);const secure=process.env.SESSION_COOKIE_SECURE==='true';res.setCookie('ld_session',out.sid,{httpOnly:true,sameSite:'lax',secure,path:'/',maxAge:60*60*8});return res.redirect(req.cookies?.ld_return_to||'/app/dashboard')}
  @Get('auth/me') async me(@Req() req:any){return this.session(req)}
  @Post('auth/logout') async logout(@Req() req:any,@Res() res:any){await this.auth.logout(req.cookies?.ld_session);res.clearCookie('ld_session',{path:'/'});return res.send({ok:true})}
  @Get('modules') async modules(@Req() req:any){await this.session(req);return{items:(await pool.query('select code,name,status from core.module order by sort_order')).rows}}

  @Get('municipalities') async municipalities(@Req() req:any,@Query('q') q=''){await this.session(req);const term=`%${q.trim()}%`;const r=await pool.query(`select ibge_code,name,uf,region,updated_at from core.municipality where $1='%%' or name ilike $1 or ibge_code ilike $1 or uf ilike $1 order by name limit 100`,[term]);return{items:r.rows}}

  @Get('sources') async sources(@Req() req:any){await this.session(req);const r=await pool.query(`select r.code,r.title,r.authority,r.access_class,r.channel,r.base_url,r.data_owner,r.cadence,r.health,r.provenance,count(s.id)::int snapshots,max(s.ingested_at) last_ingested_at from source.registry r left join source.snapshot s on s.source_id=r.id group by r.id order by r.code`);return{items:r.rows}}

  @Get('sources/coverage') async coverage(@Req() req:any,@Query('municipality') municipality?:string){await this.session(req);const r=await pool.query(`select r.code,r.title,r.authority,r.access_class,r.health,p.dataset_code,p.status publication_status,s.id snapshot_id,s.source_date,s.ingested_at,s.parser_version,s.status snapshot_status,s.quality from source.registry r left join source.publication p on p.source_id=r.id and p.status='ACTIVE' and ($1::text is null or p.municipality_ibge is null or p.municipality_ibge=$1) left join source.snapshot s on s.id=p.snapshot_id order by r.code`,[municipality||null]);return{municipality:municipality||null,items:r.rows}}

  @Post('sources/ibge/municipalities/sync')
  async syncIbge(@Req() req:any){
    await this.admin(req);
    const url='https://servicodados.ibge.gov.br/api/v1/localidades/municipios?orderBy=nome';
    const response=await fetch(url,{headers:{accept:'application/json','user-agent':'LoteDiretor/19-rc1'}});
    if(!response.ok)throw new HttpException(`ibge_http_${response.status}`,502);
    const raw=await response.text();const sha256=createHash('sha256').update(raw).digest('hex');
    let payload:any[];try{payload=JSON.parse(raw)}catch{throw new HttpException('ibge_invalid_json',502)}
    if(!Array.isArray(payload))throw new HttpException('ibge_unexpected_payload',502);
    return tx(async c=>{
      const src=await c.query(`insert into source.registry(code,title,authority,access_class,channel,base_url,data_owner,cadence,health,provenance) values('IBGE_LOCALIDADES','IBGE Localidades — Municípios','Instituto Brasileiro de Geografia e Estatística','A','REST',$1,'IBGE','ON_DEMAND','OK','{"official":true}'::jsonb) on conflict(code) do update set health='OK',base_url=excluded.base_url returning id`,[url]);
      const sourceId=src.rows[0].id;
      const snap=await c.query(`insert into source.snapshot(source_id,source_date,parser_version,sha256,metadata,status,quality,published_at) values($1,now(),'ibge-municipalities-v2',$2,$3::jsonb,'VALIDATED',$4::jsonb,now()) on conflict(source_id,sha256) do update set quality=excluded.quality,published_at=coalesce(source.snapshot.published_at,excluded.published_at) returning id`,[sourceId,sha256,JSON.stringify({url,count:payload.length}),JSON.stringify({record_count:payload.length,http_status:response.status})]);
      const snapshotId=snap.rows[0].id;let count=0;
      for(const m of payload){const code=String(m?.id||'');const name=String(m?.nome||'').trim();const uf=String(m?.microrregiao?.mesorregiao?.UF?.sigla||m?.regiao_imediata?.regiao_intermediaria?.UF?.sigla||'').trim();const region=String(m?.microrregiao?.mesorregiao?.UF?.regiao?.nome||m?.regiao_imediata?.regiao_intermediaria?.UF?.regiao?.nome||'').trim();if(!/^\d{7}$/.test(code)||!name||!uf)continue;await c.query(`insert into core.municipality(ibge_code,name,uf,region,source_snapshot_id,updated_at) values($1,$2,$3,$4,$5,now()) on conflict(ibge_code) do update set name=excluded.name,uf=excluded.uf,region=excluded.region,source_snapshot_id=excluded.source_snapshot_id,updated_at=now()`,[code,name,uf,region||null,snapshotId]);count++;}
      await c.query(`update source.publication set status='INACTIVE',deactivated_at=now() where source_id=$1 and municipality_ibge is null and (dataset_code='IBGE_LOCALIDADES' or dataset_code is null) and status='ACTIVE'`,[sourceId]);
      await c.query(`insert into source.publication(source_id,municipality_ibge,dataset_code,snapshot_id,status) values($1,null,'IBGE_LOCALIDADES',$2,'ACTIVE')`,[sourceId,snapshotId]);
      await enqueueOutbox(c,'source.snapshot.published',{source:'IBGE_LOCALIDADES',snapshotId,sha256,recordCount:count},{aggregateType:'source.snapshot',aggregateId:snapshotId,dedupeKey:`source.snapshot.published:${snapshotId}`});
      return{status:'SYNCED',source:'IBGE_LOCALIDADES',snapshotId,sha256,received:payload.length,upserted:count};
    });
  }
  @Get('dashboard')
  async dashboard(@Req() req:any){
    const session=await this.session(req);
    return tenantTx(pool,session.organizationId,async c=>{
      const modules=await c.query('select code,name,status from core.module order by sort_order');
      const properties=await c.query('select count(*)::int n from property360.property where tenant_id=$1',[session.organizationId]);
      const analyses=await c.query('select count(*)::int n from analysis.run where tenant_id=$1',[session.organizationId]);
      const reports=await c.query('select count(*)::int n from report.report_run where tenant_id=$1',[session.organizationId]);
      const notifications=await c.query("select count(*)::int n from notification.notification where tenant_id=$1 and status='UNREAD'",[session.organizationId]);
      return{session:{name:session.name,email:session.email,roles:session.roles,organizationId:session.organizationId},counters:{properties:properties.rows[0]?.n||0,analyses:analyses.rows[0]?.n||0,reports:reports.rows[0]?.n||0,unreadNotifications:notifications.rows[0]?.n||0},modules:modules.rows,version:VERSION};
    });
  }

  @Get('property360/properties')
  async properties(@Req() req:any,@Query('cursor') cursorRaw?:string,@Query('limit') limitRaw?:string){
    const session=await this.moduleSession(req,'imovel360');const limit=pageLimit(limitRaw,50,200);const cursor=decodeCursor(cursorRaw);
    if(cursorRaw&&!cursor)throw new HttpException('cursor inválido',400);
    const r=await tenantQuery(pool,session.organizationId,`select id,name,municipality_ibge,st_asgeojson(geom)::jsonb geometry,created_at from property360.property where tenant_id=$1 and ($2::timestamptz is null or (created_at,id)<($2::timestamptz,$3::uuid)) order by created_at desc,id desc limit $4`,[session.organizationId,cursor?.createdAt||null,cursor?.id||null,limit+1]);
    const hasMore=r.rows.length>limit;const items=hasMore?r.rows.slice(0,limit):r.rows;const last:any=items[items.length-1];
    return{items,hasMore,nextCursor:hasMore&&last?encodeCursor({createdAt:new Date(last.created_at).toISOString(),id:last.id}):null};
  }

  @Post('property360/properties')
  async createProperty(@Req() req:any,@Body() body:any){
    const session=await this.moduleSession(req,'imovel360');const name=String(body?.name||'Imóvel');const municipality=body?.municipality?String(body.municipality):null;const geojson=body?.geometry?JSON.stringify(body.geometry):null;
    const r=await tenantQuery(pool,session.organizationId,`insert into property360.property(tenant_id,name,municipality_ibge,geom) values($1,$2,$3,case when $4::text is null then null else st_setsrid(st_geomfromgeojson($4),4326) end) returning id,name,municipality_ibge,created_at`,[session.organizationId,name,municipality,geojson]);
    return r.rows[0];
  }

  @Get('property360/comparables')
  async comparables(@Req() req:any,@Query('municipality') municipality:string,@Query('propertyType') propertyType='APARTMENT'){
    const session=await this.moduleSession(req,'imovel360');
    const r=await tenantQuery(pool,session.organizationId,`select id,municipality_ibge,neighborhood,property_type,area_m2,price_cents,round(price_cents::numeric/100/area_m2,2) price_per_m2,source_kind,observed_at,attributes from property360.comparable where municipality_ibge=$1 and property_type=$2 order by observed_at desc nulls last limit 50`,[municipality,propertyType]);
    return{items:r.rows,warning:r.rows.some((x:any)=>x.source_kind==='DEMO')?'Existem comparáveis DEMO; não usar como laudo de mercado.':null};
  }

  @Post('property360/avm')
  async avm(@Req() req:any,@Body() body:any){
    const session=await this.moduleSession(req,'imovel360');const municipality=String(body?.municipality||'');const propertyType=String(body?.propertyType||'APARTMENT');const areaM2=asNumber(body?.areaM2,'areaM2');const propertyId=body?.propertyId?String(body.propertyId):null;if(areaM2<=0)throw new HttpException('areaM2 deve ser > 0',400);
    const key=String(req.headers?.['idempotency-key']||'').trim()||undefined;
    const idem=await withIdempotency(pool,session.organizationId,'property360.avm',key,async c=>{
      if(propertyId){const own=await c.query(`select id from property360.property where id=$1 and tenant_id=$2`,[propertyId,session.organizationId]);if(!own.rowCount)throw new HttpException('property_not_found',404);}
      const r=await c.query(`select id,source_kind,(price_cents::numeric/area_m2) cents_per_m2 from property360.comparable where municipality_ibge=$1 and property_type=$2 and area_m2>0 and price_cents>0 order by observed_at desc nulls last limit 30`,[municipality,propertyType]);
      if(r.rowCount<3)return{status:'INSUFFICIENT_DATA',estimateCents:null,comparables:r.rowCount};
      const values=r.rows.map((x:any)=>Number(x.cents_per_m2)).sort((a:number,b:number)=>a-b);const median=values[Math.floor(values.length/2)];const estimateCents=Math.round(median*areaM2);const demo=r.rows.some((x:any)=>x.source_kind==='DEMO');
      const run=await c.query(`insert into property360.avm_run(tenant_id,property_id,municipality_ibge,area_m2,model_version,status,estimate_cents,confidence,comparable_ids,assumptions) values($1,$8,$2,$3,'median-price-m2-v16','CALCULATED',$4,$5,$6::uuid[],$7::jsonb) returning id,created_at`,[session.organizationId,municipality,areaM2,estimateCents,demo?0.25:0.55,r.rows.map((x:any)=>x.id),JSON.stringify({propertyType,demo}),propertyId]);
      return{status:'CALCULATED',runId:run.rows[0].id,estimateCents,medianPricePerM2Cents:Math.round(median),comparables:r.rowCount,confidence:demo?0.25:0.55,dataClass:demo?'DEMO':'OBSERVED',warning:demo?'AVM demonstrativo. Os comparáveis DEMO não representam dados reais de mercado.':null};
    });
    return{...idem.value,idempotency:{replayed:idem.replayed,key:key||null}};
  }

  @Post('reports')
  async createReport(@Req() req:any,@Body() body:any){
    const session=await this.moduleSession(req,'relatorios');const kind=String(body?.kind||'PROPERTY360');const subjectType=String(body?.subjectType||'analysis');const subjectId=String(body?.subjectId||'');if(!subjectId)throw new HttpException('subjectId obrigatório',400);if(subjectType!=='analysis')throw new HttpException('report_subject_requires_analysis',400);const base=body?.baseDate?baseDate(String(body.baseDate)):null;
    const key=String(req.headers?.['idempotency-key']||'').trim()||undefined;
    const idem=await withIdempotency(pool,session.organizationId,'report.create.v19',key,async c=>{
      await c.query(`select set_config('app.tenant_id',$1,true)`,[session.organizationId]);
      const analysis=await c.query(`select id,base_date,property_id,input_snapshot from analysis.run where id=$1 and tenant_id=$2`,[subjectId,session.organizationId]);if(!analysis.rowCount)throw new HttpException('analysis_not_found',404);
      const template=await c.query(`select code,version from report.template where code='PROPERTY360_360' and status='ACTIVE'`);if(!template.rowCount)throw new HttpException('report_template_not_found',500);
      const reportBase=base||analysis.rows[0].base_date;
      const r=await c.query(`insert into report.report_run(tenant_id,kind,subject_type,subject_id,base_date,status,input_snapshot,template_code,template_version,metadata) values($1,$2,$3,$4,$5,'QUEUED',$6::jsonb,$7,$8,$9::jsonb) returning id,status,template_code,template_version,created_at`,[session.organizationId,kind,subjectType,subjectId,reportBase,JSON.stringify({request:body?.input||{},analysisInput:analysis.rows[0].input_snapshot,propertyId:analysis.rows[0].property_id||null}),template.rows[0].code,template.rows[0].version,JSON.stringify({requestedBy:session.email||session.id,schemaVersion:'report-360-v1'})]);
      const job=r.rows[0];
      await enqueueOutbox(c,'report.queued',{reportRunId:job.id,kind,subjectType,subjectId,baseDate:reportBase,templateCode:template.rows[0].code},{tenantId:session.organizationId,aggregateType:'report.report_run',aggregateId:job.id,dedupeKey:`report.queued:${job.id}`});
      return{...job,message:'Relatório 360 registrado e enfileirado para geração de PDF + manifesto JSON.'};
    });
    return{...idem.value,idempotency:{replayed:idem.replayed,key:key||null}};
  }
  @Get('rural/assets')
  async ruralAssets(@Req() req:any){
    const session=await this.moduleSession(req,'re-rural');
    const r=await tenantQuery(pool,session.organizationId,`select a.id,a.name,a.municipality_ibge,case when a.geom is null then null else st_area(a.geom::geography) end area_m2,a.created_at,(select count(*)::int from rural.registry_record rr where rr.asset_id=a.id) registry_records,(select count(*)::int from rural.monitor m where m.asset_id=a.id and m.status='ACTIVE') active_monitors from rural.asset a where a.tenant_id=$1 or a.tenant_id is null order by a.created_at desc limit 100`,[session.organizationId]);
    return{items:r.rows};
  }
  @Post('rural/assets')
  async createRuralAsset(@Req() req:any,@Body() body:any){
    const session=await this.moduleSession(req,'re-rural');const geometry=body?.geometry?JSON.stringify(body.geometry):null;
    const r=await tenantQuery(pool,session.organizationId,`insert into rural.asset(tenant_id,municipality_ibge,name,geom) values($1,$2,$3,case when $4::text is null then null else st_multi(st_setsrid(st_geomfromgeojson($4),4326)) end) returning id,name,municipality_ibge,created_at`,[session.organizationId,body?.municipality?String(body.municipality):null,String(body?.name||'Imóvel rural'),geometry]);
    return r.rows[0];
  }
  @Post('rural/assets/:id/registry-records')
  async createRuralRecord(@Req() req:any,@Param('id') id:string,@Body() body:any){
    const session=await this.moduleSession(req,'re-rural');const geometry=body?.geometry?JSON.stringify(body.geometry):null;
    return tenantTx(pool,session.organizationId,async c=>{
      const asset=await c.query('select id from rural.asset where id=$1 and tenant_id=$2',[id,session.organizationId]);if(!asset.rowCount)throw new HttpException('tenant_owned_asset_required',409);
      const registryType=String(body?.registryType||'UNKNOWN').toUpperCase();const snapshotId=body?.sourceSnapshotId||null;const officialTypes=new Set(['CAR','SIGEF','SNCR','CCIR','CIB','CAFIR','IBAMA_EMBARGO','PRODES','SICOR']);
      const sensitivePayload=/\"(?:cpf|cnpj|titular|proprietario|proprietário|autuado|nome_pessoa)\"\s*:/i.test(JSON.stringify(body?.attributes||{}));
      if(sensitivePayload&&!session.roles?.includes('admin'))throw new HttpException('sensitive_attributes_require_authorized_connector',403);
      if(officialTypes.has(registryType)&&!snapshotId)throw new HttpException('sourceSnapshotId obrigatório para registro oficial',400);
      if(snapshotId){const snap=await c.query(`select s.id,sr.code source_code from source.snapshot s join source.registry sr on sr.id=s.source_id where s.id=$1 and (s.validation_status='PASS' or s.status in ('VALIDATED','PUBLISHED'))`,[snapshotId]);if(!snap.rowCount)throw new HttpException('validated_snapshot_required',409);const expected:any={CAR:'CAR',SIGEF:'SIGEF',SNCR:'SNCR',CCIR:'SNCR',CIB:'CIB',CAFIR:'CIB',IBAMA_EMBARGO:'IBAMA_EMBARGO',PRODES:'PRODES',SICOR:'SICOR'};if(officialTypes.has(registryType)&&expected[registryType]&&snap.rows[0].source_code!==expected[registryType])throw new HttpException(`snapshot_source_mismatch:${expected[registryType]}`,409);}
      const r=await c.query(`insert into rural.registry_record(asset_id,source_snapshot_id,registry_type,official_identifier,attributes,geom,valid_from,valid_to) values($1,$2,$3,$4,$5::jsonb,case when $6::text is null then null else st_setsrid(st_geomfromgeojson($6),4326) end,$7,$8) returning id,registry_type,official_identifier,source_snapshot_id`,[id,snapshotId,registryType,body?.officialIdentifier||null,JSON.stringify(body?.attributes||{}),geometry,body?.validFrom||null,body?.validTo||null]);
      if(body?.officialIdentifier){const normalized=String(body.officialIdentifier).trim().toUpperCase().replace(/[^A-Z0-9]/g,'');await c.query(`insert into rural.registry_identifier(asset_id,registry_record_id,identifier_type,identifier_value,normalized_value,source_snapshot_id,status,valid_from,valid_to) values($1,$2,$3,$4,$5,$6,'OBSERVED',$7,$8) on conflict do nothing`,[id,r.rows[0].id,registryType,String(body.officialIdentifier),normalized,snapshotId,body?.validFrom||null,body?.validTo||null]);}
      if(geometry){const ghash=createHash('sha256').update(geometry).digest('hex');await c.query(`insert into rural.geometry_version(asset_id,registry_record_id,source_snapshot_id,geom,area_m2,geometry_hash,quality,valid_from,valid_to) select $1,$2,$3,geom,st_area(geom::geography),$4,$5::jsonb,valid_from,valid_to from rural.registry_record where id=$2 on conflict do nothing`,[id,r.rows[0].id,snapshotId,ghash,JSON.stringify({source:'registry_record',srid:4326})]);}
      return r.rows[0];
    });
  }
  @Post('rural/assets/:id/overlaps/recalculate')
  async ruralOverlaps(@Req() req:any,@Param('id') id:string){
    const session=await this.moduleSession(req,'re-rural');const key=String(req.headers?.['idempotency-key']||'').trim()||undefined;
    const idem=await withIdempotency(pool,session.organizationId,'rural.overlaps.recalculate',key,async c=>{
      const asset=await c.query('select id,geom from rural.asset where id=$1 and (tenant_id=$2 or tenant_id is null)',[id,session.organizationId]);if(!asset.rowCount)throw new HttpException('asset_not_found',404);if(!asset.rows[0].geom)return{status:'INSUFFICIENT_DATA',items:[],limitation:'O ativo rural não possui geometria.'};
      await c.query('delete from rural.overlap_result where asset_id=$1 and tenant_id=$2',[id,session.organizationId]);
      const r=await c.query(`insert into rural.overlap_result(tenant_id,asset_id,registry_record_id,overlap_type,overlap_area_m2,overlap_ratio,metadata) select $2,$1,rr.id,rr.registry_type,st_area(st_intersection(a.geom,rr.geom)::geography),case when st_area(a.geom::geography)>0 then st_area(st_intersection(a.geom,rr.geom)::geography)/st_area(a.geom::geography) else null end,jsonb_build_object('official_identifier',rr.official_identifier,'source_snapshot_id',rr.source_snapshot_id,'source_kind','REGISTRY_RECORD') from rural.asset a join rural.registry_record rr on rr.geom is not null and st_intersects(a.geom,rr.geom) where a.id=$1 returning id,registry_record_id,overlap_type,overlap_area_m2,overlap_ratio,metadata`,[id,session.organizationId]);
      const layers=await c.query(`insert into rural.overlap_result(tenant_id,asset_id,registry_record_id,overlap_type,overlap_area_m2,overlap_ratio,metadata) select $2,$1,null,lf.layer_code,st_area(st_intersection(a.geom,lf.geom)::geography),case when st_area(a.geom::geography)>0 then st_area(st_intersection(a.geom,lf.geom)::geography)/st_area(a.geom::geography) else null end,jsonb_build_object('official_identifier',lf.official_identifier,'source_snapshot_id',lf.source_snapshot_id,'source_kind','OFFICIAL_LAYER') from rural.asset a join rural.layer_feature lf on st_intersects(a.geom,lf.geom) where a.id=$1 and lf.source_snapshot_id in (select p.snapshot_id from source.publication p where p.status='ACTIVE') returning id,registry_record_id,overlap_type,overlap_area_m2,overlap_ratio,metadata`,[id,session.organizationId]);
      return{status:'CALCULATED',items:[...r.rows,...layers.rows],registryOverlaps:r.rowCount,layerOverlaps:layers.rowCount};
    });
    return{...idem.value,idempotency:{replayed:idem.replayed,key:key||null}};
  }
  @Post('rural/assets/:id/monitors')
  async createRuralMonitor(@Req() req:any,@Param('id') id:string,@Body() body:any){
    const session=await this.moduleSession(req,'re-rural');
    const r=await tenantQuery(pool,session.organizationId,`insert into rural.monitor(tenant_id,asset_id,monitor_type,status,configuration) select $1,id,$3,'ACTIVE',$4::jsonb from rural.asset where id=$2 and tenant_id=$1 returning id,monitor_type,status,created_at`,[session.organizationId,id,String(body?.monitorType||'REGISTRY_CHANGE'),JSON.stringify(body?.configuration||{})]);
    if(!r.rowCount)throw new HttpException('asset_not_found',404);return r.rows[0];
  }

  @Get('condominiums')
  async condominiums(@Req() req:any){const session=await this.moduleSession(req,'condominio');const r=await tenantQuery(pool,session.organizationId,`select c.id,c.name,c.kind,c.municipality_ibge,c.created_at,(select count(*)::int from condo.document d where d.condominium_id=c.id) documents,(select count(*)::int from condo.rule cr where cr.condominium_id=c.id and cr.status='CONFIRMED') confirmed_rules from condo.condominium c where c.tenant_id=$1 order by c.created_at desc`,[session.organizationId]);return{items:r.rows}}
  @Post('condominiums')
  async createCondominium(@Req() req:any,@Body() body:any){const session=await this.moduleSession(req,'condominio');const r=await tenantQuery(pool,session.organizationId,`insert into condo.condominium(tenant_id,name,kind,municipality_ibge) values($1,$2,$3,$4) returning id,name,kind,municipality_ibge,created_at`,[session.organizationId,String(body?.name||'Condomínio'),String(body?.kind||'VERTICAL'),body?.municipality||null]);return r.rows[0]}
  @Get('condominiums/:id/rules')
  async condominiumRules(@Req() req:any,@Param('id') id:string,@Query('baseDate') raw?:string){const session=await this.moduleSession(req,'condominio');const at=baseDate(raw);const r=await tenantQuery(pool,session.organizationId,`select id,rule_type,title,rule_text,status,source_locator,valid_from,valid_to,reviewed_by,reviewed_at from condo.rule where condominium_id=$1 and tenant_id=$2 and (valid_from is null or valid_from <= $3::timestamptz) and (valid_to is null or valid_to > $3::timestamptz) order by status desc,title`,[id,session.organizationId,`${at}T12:00:00Z`]);return{baseDate:at,items:r.rows}}
  @Post('condominiums/:id/rules')
  async createCondoRule(@Req() req:any,@Param('id') id:string,@Body() body:any){const session=await this.moduleSession(req,'condominio');const canConfirm=session.roles?.includes('admin')||session.roles?.includes('condo_manager');const requested=String(body?.status||'CANDIDATE').toUpperCase();const status=requested==='CONFIRMED'&&canConfirm?'CONFIRMED':'CANDIDATE';const r=await tenantQuery(pool,session.organizationId,`insert into condo.rule(tenant_id,condominium_id,document_id,rule_type,title,rule_text,status,source_locator,valid_from,valid_to,reviewed_by,reviewed_at) select $1,id,$3,$4,$5,$6,$7,$8,$9,$10,case when $7='CONFIRMED' then $11 else null end,case when $7='CONFIRMED' then now() else null end from condo.condominium where id=$2 and tenant_id=$1 returning id,title,status,created_at`,[session.organizationId,id,body?.documentId||null,String(body?.ruleType||'GENERAL'),String(body?.title||'Regra'),String(body?.ruleText||''),status,body?.sourceLocator||null,body?.validFrom||null,body?.validTo||null,session.email||session.id]);if(!r.rowCount)throw new HttpException('condominium_not_found',404);return r.rows[0]}

  @Get('municipality/workspace')
  async municipalityWorkspace(@Req() req:any){const session=await this.moduleSession(req,'prefeitura');if(!session.roles?.some((r:string)=>r==='municipality_admin'||r==='admin'))throw new HttpException('forbidden',403);const r=await tenantQuery(pool,session.organizationId,`select mt.id,mt.municipality_ibge,mt.status,mt.created_at,(select count(*)::int from municipality.document d where d.municipality_tenant_id=mt.id) documents,(select count(*)::int from municipality.rule_review rr where rr.municipality_tenant_id=mt.id and rr.status='PENDING') pending_rules,(select count(*)::int from municipality.ctm_parcel c where c.municipality_tenant_id=mt.id) ctm_parcels,(select count(*)::int from municipality.iptu_record i where i.municipality_tenant_id=mt.id) iptu_records from municipality.tenant mt where mt.organization_id=$1 order by mt.created_at desc`,[session.organizationId]);return{items:r.rows}}
  @Post('municipality/workspace')
  async createMunicipalityWorkspace(@Req() req:any,@Body() body:any){const session=await this.moduleSession(req,'prefeitura');if(!session.roles?.some((r:string)=>r==='municipality_admin'||r==='admin'))throw new HttpException('forbidden',403);const code=String(body?.municipality||'');if(!/^\d{7}$/.test(code))throw new HttpException('municipality deve ser código IBGE de 7 dígitos',400);const r=await tenantQuery(pool,session.organizationId,`insert into municipality.tenant(organization_id,municipality_ibge,status) values($1,$2,'PILOT') on conflict(municipality_ibge) do update set status=case when municipality.tenant.status='OFF' then 'PILOT' else municipality.tenant.status end where municipality.tenant.organization_id=excluded.organization_id returning *`,[session.organizationId,code]);return r.rows[0]}

  @Get('municipality/:id/rule-reviews')
  async municipalityRuleReviews(@Req() req:any,@Param('id') id:string){const session=await this.moduleSession(req,'prefeitura');if(!session.roles?.some((r:string)=>r==='municipality_admin'||r==='admin'))throw new HttpException('forbidden',403);return tenantTx(pool,session.organizationId,async c=>{const mt=await c.query('select id from municipality.tenant where id=$1 and organization_id=$2',[id,session.organizationId]);if(!mt.rowCount)throw new HttpException('municipality_workspace_not_found',404);const r=await c.query(`select rr.id review_id,rr.status review_status,rr.created_at,r.id rule_id,r.parameter,r.value_numeric,r.value_text,r.unit,r.zone_code,r.source_locator,r.condition,d.title document_title from municipality.rule_review rr join legal.rule r on r.id=rr.legal_rule_id left join legal.document_version dv on dv.id=r.source_document_version_id left join legal.document d on d.id=dv.document_id where rr.municipality_tenant_id=$1 order by rr.created_at desc limit 200`,[id]);return{items:r.rows}})}
  @Post('municipality/:id/rule-reviews/:reviewId/decide')
  async decideMunicipalityRule(@Req() req:any,@Param('id') id:string,@Param('reviewId') reviewId:string,@Body() body:any){const session=await this.moduleSession(req,'prefeitura');if(!session.roles?.some((r:string)=>r==='municipality_admin'||r==='admin'))throw new HttpException('forbidden',403);const decision=String(body?.decision||'').toUpperCase();if(!['CONFIRMED','REJECTED'].includes(decision))throw new HttpException('decision must be CONFIRMED or REJECTED',400);return tenantTx(pool,session.organizationId,async c=>{const review=await c.query(`select rr.id,rr.legal_rule_id from municipality.rule_review rr join municipality.tenant mt on mt.id=rr.municipality_tenant_id where rr.id=$1 and rr.municipality_tenant_id=$2 and mt.organization_id=$3 and rr.status='PENDING' for update`,[reviewId,id,session.organizationId]);if(!review.rowCount)throw new HttpException('pending_review_not_found',404);if(decision==='CONFIRMED'){const zone=String(body?.zoneCode||'').trim();if(!zone)throw new HttpException('zoneCode obrigatório para confirmar regra urbanística',400);await c.query(`update legal.rule set status='CONFIRMED',zone_code=$2,valid_from=coalesce($3::timestamptz,valid_from),valid_to=coalesce($4::timestamptz,valid_to) where id=$1`,[review.rows[0].legal_rule_id,zone,body?.validFrom||null,body?.validTo||null])}else{await c.query(`update legal.rule set status='REJECTED' where id=$1`,[review.rows[0].legal_rule_id])}const r=await c.query(`update municipality.rule_review set status=$2,reviewer_id=$3,reason=$4,reviewed_at=now() where id=$1 returning *`,[reviewId,decision,session.email||session.id,body?.reason||null]);return r.rows[0]})}

  @Get('solar/projects')
  async solarProjects(@Req() req:any){const session=await this.moduleSession(req,'energia-solar');const r=await tenantQuery(pool,session.organizationId,`select p.id,p.name,p.status,p.created_at,(select count(*)::int from solar.scenario s where s.project_id=p.id) scenarios from solar.project p where p.tenant_id=$1 order by p.created_at desc`,[session.organizationId]);return{items:r.rows}}
  @Post('solar/projects')
  async createSolarProject(@Req() req:any,@Body() body:any){const session=await this.moduleSession(req,'energia-solar');const r=await tenantQuery(pool,session.organizationId,`insert into solar.project(tenant_id,name,status,input_snapshot) values($1,$2,'DRAFT',$3::jsonb) returning id,name,status,created_at`,[session.organizationId,String(body?.name||'Projeto Solar'),JSON.stringify(body?.input||{})]);return r.rows[0]}
  @Post('solar/projects/:id/scenarios')
  async createSolarScenario(@Req() req:any,@Param('id') id:string,@Body() body:any){const session=await this.moduleSession(req,'energia-solar');return tenantTx(pool,session.organizationId,async c=>{const project=await c.query('select id from solar.project where id=$1 and tenant_id=$2',[id,session.organizationId]);if(!project.rowCount)throw new HttpException('solar_project_not_found',404);const r=await c.query(`insert into solar.scenario(tenant_id,project_id,name,panel_count,panel_watts,specific_yield_kwh_per_kwp,tariff_brl_per_kwh,capex_cents,status,result) values($1,$2,$3,$4,$5,$6,$7,$8,'DRAFT',$9::jsonb) returning id,name,status,created_at`,[session.organizationId,id,String(body?.name||'Cenário'),Number(body?.panelCount||1),Number(body?.panelWatts||550),body?.specificYield??null,body?.tariff??null,body?.capexCents??null,JSON.stringify(body?.result||{})]);return r.rows[0]})}

  @Get('aitec/projects')
  async aitecProjects(@Req() req:any){const session=await this.moduleSession(req,'ai-tec');const r=await tenantQuery(pool,session.organizationId,`select p.id,p.name,p.status,p.parcel_id,p.created_at,(select count(*)::int from aitec.scenario s where s.project_id=p.id) scenarios from aitec.project p where p.tenant_id=$1 order by p.created_at desc`,[session.organizationId]);return{items:r.rows}}
  @Post('aitec/projects')
  async createAitecProject(@Req() req:any,@Body() body:any){const session=await this.moduleSession(req,'ai-tec');const r=await tenantQuery(pool,session.organizationId,`insert into aitec.project(tenant_id,name,property_id,parcel_id,status) values($1,$2,$3,$4,'DRAFT') returning id,name,status,parcel_id,created_at`,[session.organizationId,String(body?.name||'Estudo de massa'),body?.propertyId||null,body?.parcelId||null]);return r.rows[0]}


  @Post('ai/chat')
  async aiChat(@Req() req:any,@Body() body:any){
    const assistant=String(body?.assistant||'cidades');const moduleCode=assistant==='condominio'?'condominio':assistant==='ai-tec'?'ai-tec':'imovel360';const session=await this.moduleSession(req,moduleCode);const at=baseDate(body?.baseDate);let rules:any[]=[];let evidence:any[]=[];let retrieval:any={enabled:false};
    await tenantTx(pool,session.organizationId,async c=>{
      if(assistant==='cidades'){
        const municipality=String(body?.municipality||'');const zoneCode=String(body?.zoneCode||'');if(municipality)retrieval={enabled:true,domains:['municipality'],municipalityIbge:municipality,topK:Number(body?.retrievalTopK||12)};if(municipality&&zoneCode){const r=await c.query(`select r.id,r.parameter,r.value_numeric,r.value_text,r.unit,r.condition,r.status,r.source_locator,r.source_document_version_id,d.title document_title from legal.rule r left join legal.document_version dv on dv.id=r.source_document_version_id left join legal.document d on d.id=dv.document_id where r.municipality_ibge=$1 and r.zone_code=$2 and r.status='CONFIRMED' and (r.valid_from is null or r.valid_from <= $3::timestamptz) and (r.valid_to is null or r.valid_to > $3::timestamptz) order by r.parameter`,[municipality,zoneCode,`${at}T12:00:00Z`]);rules=r.rows.map((x:any)=>({...x,value:x.value_numeric??x.value_text}));evidence=r.rows.map((x:any)=>({id:x.id,title:x.document_title,locator:x.source_locator,text:`${x.parameter}: ${x.value_numeric??x.value_text??''} ${x.unit||''}`}));}
      }else if(assistant==='condominio'){
        const condominiumId=String(body?.subjectId||body?.condominiumId||'');if(condominiumId){retrieval={enabled:true,domains:['condo'],scopeId:condominiumId,topK:Number(body?.retrievalTopK||12)};const exists=await c.query(`select id,name from condo.condominium where id=$1 and tenant_id=$2`,[condominiumId,session.organizationId]);if(!exists.rowCount)throw new HttpException('condominium_not_found',404);const r=await c.query(`select id,title,rule_text,status,source_locator,valid_from,valid_to from condo.rule where condominium_id=$1 and tenant_id=$2 and status='CONFIRMED' and (valid_from is null or valid_from <= $3::timestamptz) and (valid_to is null or valid_to > $3::timestamptz) order by created_at desc limit 100`,[condominiumId,session.organizationId,`${at}T12:00:00Z`]);rules=r.rows.map((x:any)=>({...x,parameter:x.title,value:x.rule_text}));const chunks=await c.query(`select dc.id,dc.chunk_index,dc.text_content,d.title document_title from condo.document_chunk dc join condo.document d on d.id=dc.document_id where dc.tenant_id=$1 and d.condominium_id=$2 order by d.created_at desc,dc.chunk_index limit 100`,[session.organizationId,condominiumId]);const decisions=await c.query(`select id,title,decision_text,source_locator,effective_from,effective_to from condo.decision where condominium_id=$1 and tenant_id=$2 and status='APPROVED' and (effective_from is null or effective_from <= $3::timestamptz) and (effective_to is null or effective_to > $3::timestamptz) order by approved_at desc limit 30`,[condominiumId,session.organizationId,`${at}T12:00:00Z`]);const context:any[]=[{id:condominiumId,title:'Condomínio',locator:'workspace',text:exists.rows[0].name}];if(body?.unitId){const u=await c.query(`select u.id,u.code,u.kind,u.floor_label,u.private_area_m2,b.name building_name from condo.unit u left join condo.building b on b.id=u.building_id where u.id=$1 and u.condominium_id=$2 and u.tenant_id=$3`,[String(body.unitId),condominiumId,session.organizationId]);if(u.rowCount)context.push({id:u.rows[0].id,title:`Unidade ${u.rows[0].code}`,locator:'unit',text:JSON.stringify(u.rows[0])});}evidence=[...context,...r.rows.map((x:any)=>({id:x.id,title:x.title,locator:x.source_locator,text:x.rule_text})),...decisions.rows.map((x:any)=>({id:x.id,title:`Deliberação: ${x.title}`,locator:x.source_locator||'assembly',text:x.decision_text})),...chunks.rows.map((x:any)=>({id:x.id,title:x.document_title,locator:`chunk:${x.chunk_index}`,text:x.text_content}))];}
      }else if(assistant==='ai-tec'){
        const projectId=String(body?.subjectId||body?.projectId||'');if(projectId){const p=await c.query(`select id,name,status from aitec.project where id=$1 and tenant_id=$2`,[projectId,session.organizationId]);if(!p.rowCount)throw new HttpException('aitec_project_not_found',404);const cs=await c.query(`select id,base_date,constraints,source_rule_ids,created_at from aitec.constraint_snapshot where project_id=$1 and tenant_id=$2 order by created_at desc limit 1`,[projectId,session.organizationId]);const sc=await c.query(`select id,status,solver_version,metrics,created_at from aitec.scenario where project_id=$1 and tenant_id=$2 order by created_at desc limit 10`,[projectId,session.organizationId]);const sol=await c.query(`select id,status,solver_version,seed,variation_index,metrics,validation,is_pareto,generated_at from aitec.solution where project_id=$1 and tenant_id=$2 order by is_pareto desc,generated_at desc limit 20`,[projectId,session.organizationId]);evidence=[...cs.rows.map((x:any)=>({id:x.id,title:'Constraint snapshot',locator:`base_date:${x.base_date}`,text:JSON.stringify(x.constraints)})),...sol.rows.map((x:any)=>({id:x.id,title:`Site solution ${x.status}${x.is_pareto?' · Pareto':''}`,locator:`solver:${x.solver_version}:seed:${x.seed}:variation:${x.variation_index}`,text:JSON.stringify({metrics:x.metrics,validation:x.validation})})),...sc.rows.map((x:any)=>({id:x.id,title:`Legacy scenario ${x.status}`,locator:`solver:${x.solver_version}`,text:JSON.stringify(x.metrics)}))];}
      }
    });
    const base=process.env.AI_GATEWAY_INTERNAL_URL||'http://ai-gateway:3003';const token=process.env.INTERNAL_API_TOKEN||'';const safeBody={assistant,message:String(body?.message||''),baseDate:at,tenantId:session.organizationId,context:{rules,evidence},retrieval};const response=await fetch(`${base}/ai/v1/chat`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:JSON.stringify(safeBody)});const data=await response.json().catch(()=>({}));if(!response.ok)throw new HttpException(data?.message||data?.error||`ai_gateway_${response.status}`,502);return data;
  }

  @Post('solar/engine/design') async solarDesign(@Req() req:any,@Body() body:any){await this.moduleSession(req,'energia-solar');const base=process.env.SOLAR_ENGINE_INTERNAL_URL||'http://solar-engine:8001';const token=process.env.INTERNAL_API_TOKEN||'';const response=await fetch(`${base}/solar/v1/design`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:JSON.stringify(body)});const data=await response.json().catch(()=>({}));if(!response.ok)throw new HttpException(data?.detail||`solar_engine_${response.status}`,502);return data}
  @Post('solar/engine/sun-position') async solarSunPosition(@Req() req:any,@Body() body:any){await this.moduleSession(req,'energia-solar');const base=process.env.SOLAR_ENGINE_INTERNAL_URL||'http://solar-engine:8001';const token=process.env.INTERNAL_API_TOKEN||'';const response=await fetch(`${base}/solar/v1/sun-position`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:JSON.stringify(body)});const data=await response.json().catch(()=>({}));if(!response.ok)throw new HttpException(data?.detail||`solar_engine_${response.status}`,502);return data}
  @Post('solar/engine/simulation') async solarSimulation(@Req() req:any,@Body() body:any){await this.moduleSession(req,'energia-solar');const base=process.env.SOLAR_ENGINE_INTERNAL_URL||'http://solar-engine:8001';const token=process.env.INTERNAL_API_TOKEN||'';const response=await fetch(`${base}/solar/v1/simulation`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:JSON.stringify(body)});const data=await response.json().catch(()=>({}));if(!response.ok)throw new HttpException(data?.detail||`solar_engine_${response.status}`,502);return data}
  @Post('aitec/engine/envelope') async aitecEnvelope(@Req() req:any,@Body() body:any){await this.moduleSession(req,'ai-tec');const base=process.env.AITEC_ENGINE_INTERNAL_URL||'http://aitec-engine:8002';const token=process.env.INTERNAL_API_TOKEN||'';const response=await fetch(`${base}/aitec/v1/envelope`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:JSON.stringify(body)});const data=await response.json().catch(()=>({}));if(!response.ok)throw new HttpException(data?.detail||`aitec_engine_${response.status}`,502);return data}
  @Post('aitec/engine/parking') async aitecParking(@Req() req:any,@Body() body:any){await this.moduleSession(req,'ai-tec');const base=process.env.AITEC_ENGINE_INTERNAL_URL||'http://aitec-engine:8002';const token=process.env.INTERNAL_API_TOKEN||'';const response=await fetch(`${base}/aitec/v1/parking`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:JSON.stringify(body)});const data=await response.json().catch(()=>({}));if(!response.ok)throw new HttpException(data?.detail||`aitec_engine_${response.status}`,502);return data}

  @Post('files/upload')
  async upload(@Req() req:any){
    const session=await this.session(req);const part=await req.file();if(!part)throw new HttpException('file_required',400);const buffer=await part.toBuffer();const max=Number(process.env.MAX_UPLOAD_BYTES||25*1024*1024);if(buffer.length>max)throw new HttpException('file_too_large',413);const sha256=createHash('sha256').update(buffer).digest('hex');const safe=String(part.filename||'arquivo').replace(/[^a-zA-Z0-9._-]+/g,'_').slice(-160);const key=`tenant/${session.organizationId}/${new Date().toISOString().slice(0,10)}/${randomUUID()}-${safe}`;
    await s3.send(new PutObjectCommand({Bucket:S3_BUCKET,Key:key,Body:buffer,ContentType:part.mimetype||'application/octet-stream',Metadata:{sha256}}));
    const r=await tenantQuery(pool,session.organizationId,`insert into core.file_object(tenant_id,object_key,bucket,filename,content_type,size_bytes,sha256,created_by) values($1,$2,$3,$4,$5,$6,$7,$8) returning id,object_key,bucket,filename,content_type,size_bytes,sha256,created_at`,[session.organizationId,key,S3_BUCKET,part.filename||safe,part.mimetype||null,buffer.length,sha256,session.email||session.id]);return r.rows[0];
  }

  @Post('condominiums/:id/documents')
  async registerCondoDocument(@Req() req:any,@Param('id') id:string,@Body() body:any){
    const session=await this.moduleSession(req,'condominio');
    return tenantTx(pool,session.organizationId,async c=>{
      const file=await c.query('select * from core.file_object where id=$1 and tenant_id=$2',[body?.fileId,session.organizationId]);if(!file.rowCount)throw new HttpException('file_not_found',404);
      const condo=await c.query('select id from condo.condominium where id=$1 and tenant_id=$2',[id,session.organizationId]);if(!condo.rowCount)throw new HttpException('condominium_not_found',404);
      const d=await c.query(`insert into condo.document(tenant_id,condominium_id,kind,title,object_key,sha256,visibility,processing_status) values($1,$2,$3,$4,$5,$6,'PRIVATE','PENDING') returning id,title,processing_status,created_at`,[session.organizationId,id,String(body?.kind||'OTHER'),String(body?.title||file.rows[0].filename),file.rows[0].object_key,file.rows[0].sha256]);
      await c.query(`insert into ingest.document_job(tenant_id,domain,document_id,object_key,sha256,status,metadata) values($1,'condo',$2,$3,$4,'QUEUED',$5::jsonb) on conflict(domain,document_id) do nothing`,[session.organizationId,d.rows[0].id,file.rows[0].object_key,file.rows[0].sha256,JSON.stringify({contentType:file.rows[0].content_type,filename:file.rows[0].filename})]);
      await enqueueOutbox(c,'document.queued',{domain:'condo',documentId:d.rows[0].id},{tenantId:session.organizationId,aggregateType:'condo.document',aggregateId:d.rows[0].id,dedupeKey:`document.queued:condo:${d.rows[0].id}`});
      return d.rows[0];
    });
  }

  @Post('municipality/:id/documents')
  async registerMunicipalityDocument(@Req() req:any,@Param('id') id:string,@Body() body:any){
    const session=await this.moduleSession(req,'prefeitura');if(!session.roles?.some((r:string)=>r==='municipality_admin'||r==='admin'))throw new HttpException('forbidden',403);
    return tenantTx(pool,session.organizationId,async c=>{
      const file=await c.query('select * from core.file_object where id=$1 and tenant_id=$2',[body?.fileId,session.organizationId]);if(!file.rowCount)throw new HttpException('file_not_found',404);
      const mt=await c.query('select id,municipality_ibge from municipality.tenant where id=$1 and organization_id=$2',[id,session.organizationId]);if(!mt.rowCount)throw new HttpException('municipality_workspace_not_found',404);
      const d=await c.query(`insert into municipality.document(municipality_tenant_id,title,kind,object_key,sha256,status,processing_status) values($1,$2,$3,$4,$5,'UPLOADED','PENDING') returning id,title,processing_status,created_at`,[id,String(body?.title||file.rows[0].filename),String(body?.kind||'LEGAL'),file.rows[0].object_key,file.rows[0].sha256]);
      await c.query(`insert into ingest.document_job(tenant_id,domain,document_id,object_key,sha256,status,metadata) values($1,'municipality',$2,$3,$4,'QUEUED',$5::jsonb) on conflict(domain,document_id) do nothing`,[session.organizationId,d.rows[0].id,file.rows[0].object_key,file.rows[0].sha256,JSON.stringify({contentType:file.rows[0].content_type,filename:file.rows[0].filename,municipalityIbge:mt.rows[0].municipality_ibge})]);
      await enqueueOutbox(c,'document.queued',{domain:'municipality',documentId:d.rows[0].id,municipalityIbge:mt.rows[0].municipality_ibge},{tenantId:session.organizationId,aggregateType:'municipality.document',aggregateId:d.rows[0].id,dedupeKey:`document.queued:municipality:${d.rows[0].id}`});
      return d.rows[0];
    });
  }

  @Get('internal/data-ops/sources') async internalDataOpsV6(@Req() req:any){const expected=process.env.INTERNAL_API_TOKEN||'';if(!expected||req.headers?.['x-internal-token']!==expected)throw new HttpException('forbidden',403);const r=await pool.query(`select r.code,r.title,r.authority,r.health,r.cadence,count(s.id)::int snapshots,max(s.ingested_at) last_ingested_at,max(s.published_at) last_published_at from source.registry r left join source.snapshot s on s.source_id=r.id group by r.id,r.code,r.title,r.authority,r.health,r.cadence order by r.code`);return{items:r.rows,version:VERSION}}
}
@Module({controllers:[ApiController],providers:[AuthService],exports:[AuthService]})
export class CoreModule{}
