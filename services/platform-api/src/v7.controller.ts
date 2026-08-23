import {Body,Controller,Get,HttpException,HttpStatus,Param,Post,Query,Req} from '@nestjs/common';
import {createHash,randomUUID} from 'crypto';
import {S3Client,PutObjectCommand} from '@aws-sdk/client-s3';
import {Pool,PoolClient} from 'pg';
import {AuthService} from './auth.service';
import {PLATFORM_VERSION} from './version';
import {withIdempotency} from './common/idempotency';
import {enqueueOutbox} from './common/outbox';
import {decodeCursor,encodeCursor,pageLimit} from './common/cursor';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});
const VERSION=PLATFORM_VERSION;
const s3=new S3Client({endpoint:process.env.S3_ENDPOINT||'http://minio:9000',region:process.env.S3_REGION||'us-east-1',forcePathStyle:true,credentials:{accessKeyId:process.env.S3_ACCESS_KEY||'lotediretor',secretAccessKey:process.env.S3_SECRET_KEY||'lotediretor-local-secret'}});
const S3_BUCKET=process.env.S3_BUCKET||'lotediretor';

type Session={id?:string;email?:string;name?:string;roles?:string[];organizationId:string;entitlements?:{modules?:string[];[key:string]:any}};

function json(value:any){return JSON.stringify(value??{});}
function dateOnly(value?:string){
  if(!value)return new Date().toISOString().slice(0,10);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value))throw new HttpException('date must use YYYY-MM-DD',400);
  return value;
}
function numberValue(value:any,name:string){const n=Number(value);if(!Number.isFinite(n))throw new HttpException(`${name} inválido`,400);return n;}

async function transaction<T>(fn:(c:PoolClient)=>Promise<T>){
  const c=await pool.connect();
  try{await c.query('BEGIN');const value=await fn(c);await c.query('COMMIT');return value;}
  catch(error){await c.query('ROLLBACK');throw error;}
  finally{c.release();}
}

async function tenantTransaction<T>(tenantId:string,fn:(c:PoolClient)=>Promise<T>){
  return transaction(async c=>{await c.query(`select set_config('app.tenant_id',$1,true)`,[tenantId]);return fn(c);});
}

@Controller('api/v1')
export class V7Controller{
  constructor(private readonly auth:AuthService){}

  private async session(req:any):Promise<Session>{
    const s=await this.auth.get(req.cookies?.ld_session) as Session|null;
    if(!s?.organizationId)throw new HttpException('unauthorized',HttpStatus.UNAUTHORIZED);
    return s;
  }
  private async requireRole(req:any,roles:string[]){
    const s=await this.session(req);
    if(!s.roles?.some(r=>roles.includes(r)))throw new HttpException('forbidden',403);
    return s;
  }
  private async moduleSession(req:any,code:string){
    const s=await this.session(req);
    const modules=Array.isArray(s.entitlements?.modules)?s.entitlements!.modules!:[];
    if(!s.roles?.includes('admin')&&!modules.includes(code))throw new HttpException('module_not_entitled',403);
    return s;
  }
  private async moduleRole(req:any,code:string,roles:string[]){
    const s=await this.moduleSession(req,code);
    if(!s.roles?.some(r=>roles.includes(r)))throw new HttpException('forbidden',403);
    return s;
  }
  private internal(req:any){
    const expected=process.env.INTERNAL_API_TOKEN||'';
    if(!expected||req.headers?.['x-internal-token']!==expected)throw new HttpException('forbidden',403);
  }

  @Get('internal/system/readiness')
  async internalReadiness(@Req() req:any){
    this.internal(req);
    const [sources,snapshots,municipalities,failedQuality]=await Promise.all([
      pool.query(`select count(*)::int n from source.registry`),
      pool.query(`select count(*)::int n from source.snapshot where validation_status='PASS' or status in ('VALIDATED','PUBLISHED')`),
      pool.query(`select count(*)::int n from core.municipality`),
      pool.query(`select count(*)::int n from data_quality.result where status='FAIL' and severity='ERROR'`)
    ]);
    return{ok:true,version:VERSION,database:'UP',sources:sources.rows[0]?.n||0,validatedSnapshots:snapshots.rows[0]?.n||0,municipalities:municipalities.rows[0]?.n||0,blockingQualityFailures:failedQuality.rows[0]?.n||0};
  }

  @Get('internal/data-ops/quality')
  async internalQuality(@Req() req:any){
    this.internal(req);
    const r=await pool.query(`select sr.code source,s.id snapshot_id,s.ingested_at,s.validation_status,s.record_count,count(q.id)::int checks,count(q.id) filter(where q.status='FAIL')::int failures,count(q.id) filter(where q.status='FAIL' and q.severity='ERROR')::int blocking_failures from source.snapshot s join source.registry sr on sr.id=s.source_id left join data_quality.result q on q.snapshot_id=s.id group by sr.code,s.id order by s.ingested_at desc limit 200`);
    return{items:r.rows,version:VERSION};
  }

  @Get('system/readiness')
  async readiness(@Req() req:any){
    const s=await this.session(req);
    return tenantTransaction(s.organizationId,async c=>{
      const queries=[] as any[];
      queries.push(await c.query(`select count(*)::int n from source.registry`));
      queries.push(await c.query(`select count(*)::int n from source.snapshot where status in ('VALIDATED','PUBLISHED') or validation_status='PASS'`));
      queries.push(await c.query(`select count(*)::int n from core.municipality`));
      queries.push(await c.query(`select count(*)::int n from property360.property where tenant_id=$1`,[s.organizationId]));
      queries.push(await c.query(`select count(*)::int n from analysis.run where tenant_id=$1 and status='COMPLETED'`,[s.organizationId]));
      queries.push(await c.query(`select count(*)::int n from rural.asset where tenant_id=$1`,[s.organizationId]));
      queries.push(await c.query(`select count(*)::int n from condo.condominium where tenant_id=$1`,[s.organizationId]));
      queries.push(await c.query(`select count(*)::int n from solar.project where tenant_id=$1`,[s.organizationId]));
      queries.push(await c.query(`select count(*)::int n from aitec.project where tenant_id=$1`,[s.organizationId]));
      queries.push(await c.query(`select count(*)::int n from report.report_run where tenant_id=$1 and status='COMPLETED'`,[s.organizationId]));
      const counts=queries.map(x=>x.rows[0]?.n||0);
      return{version:VERSION,milestone:'V19_CORE_CLOSURE_ALPHA',live:{sources:counts[0],validatedSnapshots:counts[1],municipalities:counts[2],properties:counts[3],completedAnalyses:counts[4],ruralAssets:counts[5],condominiums:counts[6],solarProjects:counts[7],aitecProjects:counts[8],completedReports:counts[9]},caveats:['Percentual de código não equivale a cobertura nacional de dados. Fontes licenciadas/credenciadas só contam como cobertura quando snapshots reais estão publicados.','Homologação de produção exige execução Docker/E2E e testes de isolamento com usuário PostgreSQL non-owner.']};
    });
  }

  @Get('sources/:code/snapshots')
  async sourceSnapshots(@Req() req:any,@Param('code') code:string){
    await this.session(req);
    const r=await pool.query(`select s.id,s.source_date,s.ingested_at,s.parser_version,s.sha256,s.status,s.validation_status,s.record_count,s.schema_version,s.quality,s.published_at,
      exists(select 1 from source.publication p where p.snapshot_id=s.id and p.status='ACTIVE') active
      from source.snapshot s join source.registry r on r.id=s.source_id where r.code=$1 order by s.ingested_at desc limit 100`,[code]);
    return{source:code,items:r.rows};
  }

  @Post('sources/:code/quality')
  async recordQuality(@Req() req:any,@Param('code') code:string,@Body() body:any){
    const s=await this.requireRole(req,['admin']);
    const snapshotId=String(body?.snapshotId||'');
    const checks=Array.isArray(body?.checks)?body.checks:[];
    if(!snapshotId||!checks.length)throw new HttpException('snapshotId e checks são obrigatórios',400);
    return tenantTransaction(s.organizationId,async c=>{
      const snap=await c.query(`select s.id,s.source_id from source.snapshot s join source.registry r on r.id=s.source_id where s.id=$1 and r.code=$2`,[snapshotId,code]);
      if(!snap.rowCount)throw new HttpException('snapshot_not_found',404);
      let failures=0;
      for(const item of checks){
        const status=String(item?.status||'SKIP').toUpperCase();
        const severity=String(item?.severity||'INFO').toUpperCase();
        if(!['PASS','FAIL','SKIP'].includes(status)||!['INFO','WARN','ERROR'].includes(severity))throw new HttpException('quality check inválido',400);
        if(status==='FAIL'&&severity==='ERROR')failures++;
        await c.query(`insert into data_quality.result(source_id,snapshot_id,check_code,severity,status,expected,observed)
          values($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb)
          on conflict(snapshot_id,check_code) do update set severity=excluded.severity,status=excluded.status,expected=excluded.expected,observed=excluded.observed,checked_at=now()`,
          [snap.rows[0].source_id,snapshotId,String(item?.code||'UNKNOWN'),severity,status,json(item?.expected||{}),json(item?.observed||{})]);
      }
      await c.query(`update source.snapshot set validation_status=$2,status=case when $2='PASS' then 'VALIDATED' else status end where id=$1`,[snapshotId,failures?'FAIL':'PASS']);
      await c.query(`insert into audit.event(tenant_id,action,object_type,object_id,metadata) values($1,'DATA_QUALITY_REVIEW','source.snapshot',$2,$3::jsonb)`,[s.organizationId,snapshotId,json({source:code,checks:checks.length,failures})]);
      return{snapshotId,validationStatus:failures?'FAIL':'PASS',checks:checks.length,blockingFailures:failures};
    });
  }

  @Post('sources/:code/publications/activate')
  async activatePublication(@Req() req:any,@Param('code') code:string,@Body() body:any){
    const s=await this.requireRole(req,['admin']);
    const snapshotId=String(body?.snapshotId||'');
    const municipality=body?.municipality?String(body.municipality):null;
    const action=String(body?.action||'ACTIVATE').toUpperCase();
    if(!['ACTIVATE','ROLLBACK'].includes(action))throw new HttpException('action inválida',400);
    return transaction(async c=>{
      const target=await c.query(`select s.id,s.source_id,s.validation_status,s.status,nullif(s.metadata->>'dataset_code','') snapshot_dataset_code from source.snapshot s join source.registry r on r.id=s.source_id where s.id=$1 and r.code=$2`,[snapshotId,code]);
      if(!target.rowCount)throw new HttpException('snapshot_not_found',404);
      if(target.rows[0].validation_status!=='PASS'&&target.rows[0].status!=='VALIDATED')throw new HttpException('snapshot_not_validated',409);
      const datasetCode=body?.datasetCode?String(body.datasetCode):target.rows[0].snapshot_dataset_code||null;
      const previous=await c.query(`select id,snapshot_id from source.publication where source_id=$1 and municipality_ibge is not distinct from $2 and dataset_code is not distinct from $3 and status='ACTIVE' for update`,[target.rows[0].source_id,municipality,datasetCode]);
      if(previous.rowCount)await c.query(`update source.publication set status='INACTIVE',deactivated_at=now() where id=$1`,[previous.rows[0].id]);
      const published=await c.query(`insert into source.publication(source_id,municipality_ibge,dataset_code,snapshot_id,status) values($1,$2,$3,$4,'ACTIVE') returning *`,[target.rows[0].source_id,municipality,datasetCode,snapshotId]);
      await c.query(`update source.snapshot set status='PUBLISHED',published_at=coalesce(published_at,now()) where id=$1`,[snapshotId]);
      await c.query(`insert into source.publication_event(source_id,municipality_ibge,dataset_code,previous_snapshot_id,next_snapshot_id,action,actor,reason) values($1,$2,$3,$4,$5,$6,$7,$8)`,[target.rows[0].source_id,municipality,datasetCode,previous.rows[0]?.snapshot_id||null,snapshotId,action,s.email||s.id||'admin',body?.reason||null]);
      return{status:'ACTIVE',datasetCode,publication:published.rows[0],previousSnapshotId:previous.rows[0]?.snapshot_id||null,action};
    });
  }

  @Get('data-quality')
  async dataQuality(@Req() req:any,@Query('source') source?:string){
    await this.session(req);
    const r=await pool.query(`select sr.code source,s.id snapshot_id,s.ingested_at,s.validation_status,s.record_count,
      count(q.id)::int checks,count(q.id) filter(where q.status='FAIL')::int failures,
      count(q.id) filter(where q.status='FAIL' and q.severity='ERROR')::int blocking_failures
      from source.snapshot s join source.registry sr on sr.id=s.source_id left join data_quality.result q on q.snapshot_id=s.id
      where ($1::text is null or sr.code=$1) group by sr.code,s.id order by s.ingested_at desc limit 200`,[source||null]);
    return{items:r.rows};
  }


  @Get('evidence/search')
  async evidenceSearch(@Req() req:any,@Query('q') q='',@Query('domain') domain?:string,@Query('baseDate') baseDateRaw?:string){
    const s=await this.session(req);const term=q.trim();if(term.length<2)throw new HttpException('q deve ter ao menos 2 caracteres',400);const at=dateOnly(baseDateRaw);
    const allowed=domain?String(domain):null;if(allowed&&!['condo','municipality'].includes(allowed))throw new HttpException('domain inválido',400);
    if(allowed==='condo')await this.moduleSession(req,'condominio');if(allowed==='municipality')await this.moduleSession(req,'prefeitura');
    return tenantTransaction(s.organizationId,async c=>{
      const chunks=await c.query(`select id,domain,document_id,chunk_index,left(text_content,1800) text_content,metadata,ts_rank(to_tsvector('portuguese',text_content),plainto_tsquery('portuguese',$2)) rank from ingest.document_text where tenant_id=$1 and ($3::text is null or domain=$3) and to_tsvector('portuguese',text_content) @@ plainto_tsquery('portuguese',$2) order by rank desc,created_at desc limit 40`,[s.organizationId,term,allowed]);
      const rules=await c.query(`select r.id,r.municipality_ibge,r.zone_code,r.parameter,r.value_numeric,r.value_text,r.unit,r.condition,r.source_document_version_id,r.source_locator,r.valid_from,r.valid_to from legal.rule r where r.status='CONFIRMED' and (r.valid_from is null or r.valid_from <= $1::timestamptz) and (r.valid_to is null or r.valid_to > $1::timestamptz) and (r.parameter ilike $2 or coalesce(r.value_text,'') ilike $2 or coalesce(r.condition::text,'') ilike $2) order by r.created_at desc limit 40`,[`${at}T12:00:00Z`,`%${term}%`]);
      return{query:term,domain:allowed,baseDate:at,chunks:chunks.rows,rules:rules.rows,searchMode:'POSTGRES_FTS_AND_CONFIRMED_RULES',limitations:['OpenSearch é aceleração opcional; resultado técnico continua dependente de evidência, vigência e regra confirmada.']};
    });
  }

  @Get('property360/developments')
  async developments(@Req() req:any,@Query('cursor') cursorRaw?:string,@Query('limit') limitRaw?:string){
    const s=await this.moduleSession(req,'imovel360');const limit=pageLimit(limitRaw,50,200);const cursor=decodeCursor(cursorRaw);if(cursorRaw&&!cursor)throw new HttpException('cursor inválido',400);
    return tenantTransaction(s.organizationId,async c=>{const r=await c.query(`select id,name,municipality_ibge,status,gross_land_area_m2,attributes,created_at,updated_at from property360.development where tenant_id=$1 and ($2::timestamptz is null or (created_at,id)<($2::timestamptz,$3::uuid)) order by created_at desc,id desc limit $4`,[s.organizationId,cursor?.createdAt||null,cursor?.id||null,limit+1]);const hasMore=r.rows.length>limit;const items=hasMore?r.rows.slice(0,limit):r.rows;const last=items[items.length-1];return{items,hasMore,nextCursor:hasMore&&last?encodeCursor({createdAt:new Date(last.created_at).toISOString(),id:last.id}):null};});
  }
  @Post('property360/developments')
  async createDevelopment(@Req() req:any,@Body() body:any){
    const s=await this.moduleSession(req,'imovel360');const geometry=body?.geometry?json(body.geometry):null;
    return tenantTransaction(s.organizationId,async c=>{
      const r=await c.query(`insert into property360.development(tenant_id,name,municipality_ibge,status,geom,gross_land_area_m2,attributes)
        values($1,$2,$3,$4,case when $5::text is null then null else st_setsrid(st_geomfromgeojson($5),4326) end,$6,$7::jsonb)
        returning id,name,municipality_ibge,status,gross_land_area_m2,attributes,created_at`,[s.organizationId,String(body?.name||'Empreendimento'),body?.municipality||null,String(body?.status||'PROSPECT'),geometry,body?.grossLandAreaM2??null,json(body?.attributes||{})]);
      return r.rows[0];
    });
  }

  @Get('property360/crm/leads')
  async leads(@Req() req:any,@Query('stage') stage?:string,@Query('cursor') cursorRaw?:string,@Query('limit') limitRaw?:string){
    const s=await this.moduleSession(req,'imovel360');const limit=pageLimit(limitRaw,50,200);const cursor=decodeCursor(cursorRaw);if(cursorRaw&&!cursor)throw new HttpException('cursor inválido',400);
    return tenantTransaction(s.organizationId,async c=>{const r=await c.query(`select id,name,stage,score,owner_user_id,contact,tags,notes,property_id,development_id,created_at,updated_at from crm.lead where tenant_id=$1 and ($2::text is null or stage=$2) and ($3::timestamptz is null or (created_at,id)<($3::timestamptz,$4::uuid)) order by created_at desc,id desc limit $5`,[s.organizationId,stage||null,cursor?.createdAt||null,cursor?.id||null,limit+1]);const hasMore=r.rows.length>limit;const items=hasMore?r.rows.slice(0,limit):r.rows;const last=items[items.length-1];return{items,hasMore,nextCursor:hasMore&&last?encodeCursor({createdAt:new Date(last.created_at).toISOString(),id:last.id}):null};});
  }
  @Post('property360/crm/leads')
  async createLead(@Req() req:any,@Body() body:any){const s=await this.moduleSession(req,'imovel360');return tenantTransaction(s.organizationId,async c=>(await c.query(`insert into crm.lead(tenant_id,property_id,development_id,name,stage,score,owner_user_id,contact,tags,notes) values($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10) returning *`,[s.organizationId,body?.propertyId||null,body?.developmentId||null,String(body?.name||'Lead'),String(body?.stage||'NEW'),Number(body?.score||0),body?.ownerUserId||null,json(body?.contact||{}),Array.isArray(body?.tags)?body.tags:[],body?.notes||null])).rows[0]);}

  @Get('property360/market/snapshots')
  async marketSnapshots(@Req() req:any,@Query('municipality') municipality?:string){const s=await this.moduleSession(req,'imovel360');return tenantTransaction(s.organizationId,async c=>({items:(await c.query(`select id,municipality_ibge,reference_date,metrics,data_class,source_snapshot_id,created_at from property360.market_snapshot where (tenant_id is null or tenant_id=$1) and ($2::text is null or municipality_ibge=$2) order by reference_date desc limit 100`,[s.organizationId,municipality||null])).rows}));}

  @Get('rural/layers')
  async ruralLayers(@Req() req:any){await this.moduleSession(req,'re-rural');const r=await pool.query(`select lc.code,lc.title,lc.authority,lc.legal_nature,lc.status,lc.metadata,count(lf.id)::int features,max(ss.ingested_at) last_ingested_at from rural.layer_catalog lc left join rural.layer_feature lf on lf.layer_code=lc.code left join source.snapshot ss on ss.id=lf.source_snapshot_id group by lc.code order by lc.code`);return{items:r.rows};}

  @Post('rural/layers/:code/features/import')
  async importRuralFeatures(@Req() req:any,@Param('code') code:string,@Body() body:any){
    await this.moduleRole(req,'re-rural',['admin']);const snapshotId=String(body?.sourceSnapshotId||'');const features=Array.isArray(body?.features)?body.features:[];
    if(!snapshotId||!features.length)throw new HttpException('sourceSnapshotId e features são obrigatórios',400);
    return transaction(async c=>{
      const layer=await c.query(`select code from rural.layer_catalog where code=$1`,[code]);if(!layer.rowCount)throw new HttpException('layer_not_found',404);
      const snap=await c.query(`select id from source.snapshot where id=$1 and (validation_status='PASS' or status in ('VALIDATED','PUBLISHED'))`,[snapshotId]);if(!snap.rowCount)throw new HttpException('validated_snapshot_required',409);
      let loaded=0;
      for(const f of features){if(!f?.geometry)continue;await c.query(`insert into rural.layer_feature(layer_code,source_snapshot_id,official_identifier,geom,attributes,valid_from,valid_to) values($1,$2,$3,st_setsrid(st_geomfromgeojson($4),4326),$5::jsonb,$6,$7)`,[code,snapshotId,f.officialIdentifier||null,json(f.geometry),json(f.attributes||{}),f.validFrom||null,f.validTo||null]);loaded++;}
      return{layer:code,snapshotId,received:features.length,loaded};
    });
  }

  @Get('rural/assets/:id/detail')
  async ruralAssetDetail(@Req() req:any,@Param('id') id:string){
    const s=await this.moduleSession(req,'re-rural');return tenantTransaction(s.organizationId,async c=>{
      const asset=await c.query(`select id,name,municipality_ibge,st_asgeojson(geom)::jsonb geometry,case when geom is null then null else st_area(geom::geography) end area_m2,created_at from rural.asset where id=$1 and (tenant_id=$2 or tenant_id is null)`,[id,s.organizationId]);
      if(!asset.rowCount)throw new HttpException('asset_not_found',404);
      const [records,overlaps,monitors]=await Promise.all([
        c.query(`select id,registry_type,official_identifier,attributes,source_snapshot_id,valid_from,valid_to from rural.registry_record where asset_id=$1 order by registry_type`,[id]),
        c.query(`select id,overlap_type,overlap_area_m2,overlap_ratio,metadata,calculated_at from rural.overlap_result where asset_id=$1 order by calculated_at desc`,[id]),
        c.query(`select m.id,m.monitor_type,m.status,m.last_checked_at,m.last_change_at,m.configuration,m.created_at,(select count(*)::int from rural.monitor_event e where e.monitor_id=m.id) events from rural.monitor m where m.asset_id=$1 and m.tenant_id=$2 order by m.created_at desc`,[id,s.organizationId])
      ]);
      return{asset:asset.rows[0],registryRecords:records.rows,overlaps:overlaps.rows,monitors:monitors.rows};
    });
  }

  @Get('rural/monitors/:id/events')
  async ruralMonitorEvents(@Req() req:any,@Param('id') id:string){const s=await this.moduleSession(req,'re-rural');return tenantTransaction(s.organizationId,async c=>({items:(await c.query(`select e.* from rural.monitor_event e join rural.monitor m on m.id=e.monitor_id where e.monitor_id=$1 and e.tenant_id=$2 and m.tenant_id=$2 order by detected_at desc`,[id,s.organizationId])).rows}));}

  @Get('condominiums/:id/evidence')
  async condominiumEvidence(@Req() req:any,@Param('id') id:string,@Query('q') q=''){
    const s=await this.moduleSession(req,'condominio');const term=`%${q.trim()}%`;
    return tenantTransaction(s.organizationId,async c=>{
      const exists=await c.query(`select id from condo.condominium where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!exists.rowCount)throw new HttpException('condominium_not_found',404);
      const chunks=await c.query(`select dc.id chunk_id,dc.document_id,dc.chunk_index,dc.text_content,dc.metadata,d.title document_title,d.sha256 from condo.document_chunk dc join condo.document d on d.id=dc.document_id where dc.tenant_id=$1 and d.condominium_id=$2 and ($3='%%' or dc.text_content ilike $3) order by d.created_at desc,dc.chunk_index limit 50`,[s.organizationId,id,term]);
      const rules=await c.query(`select id,title,rule_text,status,source_locator,valid_from,valid_to from condo.rule where tenant_id=$1 and condominium_id=$2 and ($3='%%' or title ilike $3 or rule_text ilike $3) order by status desc,created_at desc limit 50`,[s.organizationId,id,term]);
      return{query:q,chunks:chunks.rows,rules:rules.rows};
    });
  }

  @Post('condominiums/:id/rules/:ruleId/review')
  async reviewCondoRule(@Req() req:any,@Param('id') id:string,@Param('ruleId') ruleId:string,@Body() body:any){
    const s=await this.moduleRole(req,'condominio',['admin','condo_manager']);const decision=String(body?.decision||'').toUpperCase();if(!['CONFIRMED','REJECTED'].includes(decision))throw new HttpException('decision must be CONFIRMED or REJECTED',400);
    return tenantTransaction(s.organizationId,async c=>{
      const r=await c.query(`update condo.rule set status=$4,reviewed_by=$3,reviewed_at=now(),valid_from=coalesce($5::timestamptz,valid_from),valid_to=coalesce($6::timestamptz,valid_to) where id=$1 and condominium_id=$2 and tenant_id=$7 and status='CANDIDATE' returning *`,[ruleId,id,s.email||s.id||'reviewer',decision,body?.validFrom||null,body?.validTo||null,s.organizationId]);
      if(!r.rowCount)throw new HttpException('candidate_rule_not_found',404);return r.rows[0];
    });
  }

  @Get('municipality/:id/ctm')
  async municipalityCtm(@Req() req:any,@Param('id') id:string,@Query('q') q=''){
    const s=await this.moduleRole(req,'prefeitura',['admin','municipality_admin']);const term=`%${q.trim()}%`;
    return tenantTransaction(s.organizationId,async c=>({items:(await c.query(`select cp.id,cp.cadastral_code,cp.attributes,cp.source_snapshot_id,cp.valid_from,cp.valid_to,case when cp.geom is null then null else st_area(cp.geom::geography) end area_m2 from municipality.ctm_parcel cp join municipality.tenant mt on mt.id=cp.municipality_tenant_id where cp.municipality_tenant_id=$1 and mt.organization_id=$2 and ($3='%%' or cp.cadastral_code ilike $3) order by cp.cadastral_code limit 200`,[id,s.organizationId,term])).rows}));
  }

  @Post('municipality/:id/ctm/import')
  async importCtm(@Req() req:any,@Param('id') id:string,@Body() body:any){
    const s=await this.moduleRole(req,'prefeitura',['admin','municipality_admin']);const records=Array.isArray(body?.records)?body.records:[];if(!records.length)throw new HttpException('records são obrigatórios',400);
    return tenantTransaction(s.organizationId,async c=>{
      const mt=await c.query(`select id,municipality_ibge from municipality.tenant where id=$1 and organization_id=$2`,[id,s.organizationId]);if(!mt.rowCount)throw new HttpException('municipality_workspace_not_found',404);
      const raw=json(records);const sha=createHash('sha256').update(raw).digest('hex');const sourceCode=`MUNICIPALITY_CTM_${mt.rows[0].municipality_ibge}`;
      const src=await c.query(`insert into source.registry(code,title,authority,access_class,channel,data_owner,cadence,health,provenance) values($1,$2,$3,'B','UPLOAD',$3,'ON_DEMAND','OK',$4::jsonb) on conflict(code) do update set health='OK' returning id`,[sourceCode,`CTM municipal ${mt.rows[0].municipality_ibge}`,String(body?.authority||'Prefeitura'),json({municipality:mt.rows[0].municipality_ibge,uploaded:true})]);
      const snap=await c.query(`insert into source.snapshot(source_id,source_date,parser_version,sha256,metadata,status,quality,published_at,record_count,validation_status,schema_version) values($1,now(),'ctm-json-v1',$2,$3::jsonb,'VALIDATED',$4::jsonb,now(),$5,'PASS','ctm-v1') on conflict(source_id,sha256) do update set record_count=excluded.record_count,validation_status='PASS' returning id`,[src.rows[0].id,sha,json({workspace:id}),json({record_count:records.length}),records.length]);
      const importRun=await c.query(`insert into municipality.ctm_import(municipality_tenant_id,tenant_id,source_snapshot_id,filename,sha256,status,records_received) values($1,$2,$3,$4,$5,'RUNNING',$6) returning id`,[id,s.organizationId,snap.rows[0].id,body?.filename||'api.json',sha,records.length]);
      let loaded=0;const errors:any[]=[];
      for(const [index,r] of records.entries()){
        try{const code=String(r?.cadastralCode||'').trim();if(!code)throw new Error('cadastralCode ausente');const geometry=r?.geometry?json(r.geometry):null;await c.query(`insert into municipality.ctm_parcel(municipality_tenant_id,cadastral_code,geom,attributes,source_snapshot_id,valid_from,valid_to) values($1,$2,case when $3::text is null then null else st_multi(st_setsrid(st_geomfromgeojson($3),4326)) end,$4::jsonb,$5,$6,$7) on conflict(municipality_tenant_id,cadastral_code,valid_from) do update set geom=excluded.geom,attributes=excluded.attributes,source_snapshot_id=excluded.source_snapshot_id,valid_to=excluded.valid_to`,[id,code,geometry,json(r?.attributes||{}),snap.rows[0].id,r?.validFrom||null,r?.validTo||null]);loaded++;}catch(e:any){errors.push({index,message:e?.message||String(e)});}
      }
      await c.query(`update municipality.ctm_import set status=$2,records_loaded=$3,errors=$4::jsonb,completed_at=now() where id=$1`,[importRun.rows[0].id,errors.length?'COMPLETED_WITH_ERRORS':'COMPLETED',loaded,json(errors.slice(0,100))]);
      return{importId:importRun.rows[0].id,snapshotId:snap.rows[0].id,sha256:sha,received:records.length,loaded,errors:errors.length};
    });
  }

  @Get('municipality/:id/iptu')
  async municipalityIptu(@Req() req:any,@Param('id') id:string,@Query('year') yearRaw?:string){
    const s=await this.moduleRole(req,'prefeitura',['admin','municipality_admin']);const year=yearRaw?Number(yearRaw):null;
    return tenantTransaction(s.organizationId,async c=>({items:(await c.query(`select ir.id,ir.cadastral_code,ir.reference_year,ir.land_value_cents,ir.building_value_cents,ir.tax_value_cents,ir.attributes from municipality.iptu_record ir join municipality.tenant mt on mt.id=ir.municipality_tenant_id where ir.municipality_tenant_id=$1 and mt.organization_id=$2 and ($3::int is null or ir.reference_year=$3) order by ir.reference_year desc,ir.cadastral_code limit 500`,[id,s.organizationId,year])).rows}));
  }

  @Post('municipality/:id/iptu/import')
  async importIptu(@Req() req:any,@Param('id') id:string,@Body() body:any){
    const s=await this.moduleRole(req,'prefeitura',['admin','municipality_admin']);const records=Array.isArray(body?.records)?body.records:[];if(!records.length)throw new HttpException('records são obrigatórios',400);
    return tenantTransaction(s.organizationId,async c=>{const mt=await c.query(`select id from municipality.tenant where id=$1 and organization_id=$2`,[id,s.organizationId]);if(!mt.rowCount)throw new HttpException('municipality_workspace_not_found',404);let loaded=0;for(const r of records){const code=String(r?.cadastralCode||'').trim();const year=Number(r?.referenceYear);if(!code||!Number.isInteger(year))continue;await c.query(`insert into municipality.iptu_record(municipality_tenant_id,cadastral_code,reference_year,land_value_cents,building_value_cents,tax_value_cents,attributes) values($1,$2,$3,$4,$5,$6,$7::jsonb) on conflict(municipality_tenant_id,cadastral_code,reference_year) do update set land_value_cents=excluded.land_value_cents,building_value_cents=excluded.building_value_cents,tax_value_cents=excluded.tax_value_cents,attributes=excluded.attributes`,[id,code,year,r?.landValueCents??null,r?.buildingValueCents??null,r?.taxValueCents??null,json(r?.attributes||{})]);loaded++;}return{received:records.length,loaded};});
  }

  @Get('solar/projects/:id')
  async solarProject(@Req() req:any,@Param('id') id:string){const s=await this.moduleSession(req,'energia-solar');return tenantTransaction(s.organizationId,async c=>{const p=await c.query(`select id,name,status,input_snapshot,created_at from solar.project where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!p.rowCount)throw new HttpException('solar_project_not_found',404);const scenarios=await c.query(`select id,name,panel_count,panel_watts,specific_yield_kwh_per_kwp,tariff_brl_per_kwh,capex_cents,status,result,created_at from solar.scenario where project_id=$1 and tenant_id=$2 order by created_at desc`,[id,s.organizationId]);return{project:p.rows[0],scenarios:scenarios.rows};});}

  @Post('solar/projects/:id/simulate')
  async simulateSolarProject(@Req() req:any,@Param('id') id:string,@Body() body:any){
    const s=await this.moduleSession(req,'energia-solar');const key=String(req.headers?.['idempotency-key']||'').trim()||undefined;
    const idem=await withIdempotency(pool,s.organizationId,`solar.simulate:${id}`,key,async c=>{
      await c.query(`select set_config('app.tenant_id',$1,true)`,[s.organizationId]);
      const project=await c.query(`select id from solar.project where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!project.rowCount)throw new HttpException('solar_project_not_found',404);
      const input={panel_count:Number(body?.panelCount||0),panel_watts:Number(body?.panelWatts||0),specific_yield_kwh_per_kwp:body?.specificYield??null,tariff_brl_per_kwh:body?.tariff??null,capex_brl:body?.capexBrl??null,years:body?.years??25,annual_tariff_escalation:body?.annualTariffEscalation??0.04,annual_degradation:body?.annualDegradation??0.005,monthly_distribution:body?.monthlyDistribution??null};
      const base=process.env.SOLAR_ENGINE_INTERNAL_URL||'http://solar-engine:8001';const token=process.env.INTERNAL_API_TOKEN||'';
      const response=await fetch(`${base}/solar/v1/simulation`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:json(input)});const output=await response.json().catch(()=>({}));if(!response.ok)throw new HttpException(output?.detail||`solar_engine_${response.status}`,502);
      const scenario=await c.query(`insert into solar.scenario(tenant_id,project_id,name,panel_count,panel_watts,specific_yield_kwh_per_kwp,tariff_brl_per_kwh,capex_cents,status,result) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb) returning id,name,status,created_at`,[s.organizationId,id,String(body?.name||'Simulação'),input.panel_count,input.panel_watts,input.specific_yield_kwh_per_kwp,input.tariff_brl_per_kwh,input.capex_brl==null?null:Math.round(Number(input.capex_brl)*100),output?.status==='CALCULATED_FROM_INPUT_ASSUMPTIONS'?'CALCULATED':'REQUIRES_INPUT',json(output)]);
      const run=await c.query(`insert into solar.simulation_run(tenant_id,project_id,scenario_id,engine_version,status,input_snapshot,output_snapshot) values($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb) returning id,created_at`,[s.organizationId,id,scenario.rows[0].id,PLATFORM_VERSION,scenario.rows[0].status,json(input),json(output)]);
      await enqueueOutbox(c,'solar.scenario.completed',{projectId:id,scenarioId:scenario.rows[0].id,simulationRunId:run.rows[0].id,status:scenario.rows[0].status},{tenantId:s.organizationId,aggregateType:'solar.scenario',aggregateId:scenario.rows[0].id,dedupeKey:`solar.scenario.completed:${scenario.rows[0].id}`});
      return{scenario:scenario.rows[0],run:run.rows[0],result:output};
    });
    return{...idem.value,idempotency:{replayed:idem.replayed,key:key||null}};
  }
  @Get('aitec/projects/:id')
  async aitecProject(@Req() req:any,@Param('id') id:string){const s=await this.moduleSession(req,'ai-tec');return tenantTransaction(s.organizationId,async c=>{const p=await c.query(`select id,name,status,property_id,parcel_id,created_at from aitec.project where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!p.rowCount)throw new HttpException('aitec_project_not_found',404);const [constraints,scenarios,units]=await Promise.all([c.query(`select id,parcel_id,base_date,constraints,source_rule_ids,created_at from aitec.constraint_snapshot where project_id=$1 and tenant_id=$2 order by created_at desc`,[id,s.organizationId]),c.query(`select id,constraint_snapshot_id,solver_version,status,metrics,artifact_key,created_at from aitec.scenario where project_id=$1 and tenant_id=$2 order by created_at desc`,[id,s.organizationId]),c.query(`select id,unit_type,target_area_m2,quantity,metadata from aitec.unit_program where project_id=$1 and tenant_id=$2 order by created_at`,[id,s.organizationId])]);return{project:p.rows[0],constraints:constraints.rows,scenarios:scenarios.rows,unitProgram:units.rows};});}

  @Post('aitec/projects/:id/constraints')
  async createAitecConstraints(@Req() req:any,@Param('id') id:string,@Body() body:any){const s=await this.moduleSession(req,'ai-tec');return tenantTransaction(s.organizationId,async c=>{const project=await c.query(`select id,parcel_id from aitec.project where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!project.rowCount)throw new HttpException('aitec_project_not_found',404);const r=await c.query(`insert into aitec.constraint_snapshot(tenant_id,project_id,parcel_id,base_date,constraints,source_rule_ids) values($1,$2,$3,$4,$5::jsonb,$6::uuid[]) returning *`,[s.organizationId,id,body?.parcelId||project.rows[0].parcel_id||null,dateOnly(body?.baseDate),json(body?.constraints||{}),Array.isArray(body?.sourceRuleIds)?body.sourceRuleIds:[]]);return r.rows[0];});}

  @Post('aitec/projects/:id/scenarios/generate')
  async generateAitecScenario(@Req() req:any,@Param('id') id:string,@Body() body:any){
    const s=await this.moduleSession(req,'ai-tec');if(!body?.polygon)throw new HttpException('polygon é obrigatório',400);const key=String(req.headers?.['idempotency-key']||'').trim()||undefined;
    const idem=await withIdempotency(pool,s.organizationId,`aitec.generate:${id}`,key,async c=>{
      await c.query(`select set_config('app.tenant_id',$1,true)`,[s.organizationId]);
      const project=await c.query(`select id from aitec.project where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!project.rowCount)throw new HttpException('aitec_project_not_found',404);
      const base=process.env.AITEC_ENGINE_INTERNAL_URL||'http://aitec-engine:8002';const token=process.env.INTERNAL_API_TOKEN||'';
      const directional=Array.isArray(body?.directionalSetbacks)&&body.directionalSetbacks.length>0;const envelopePath=directional?'/aitec/v1/envelope-directional':'/aitec/v1/envelope';const envelopeInput=directional?{polygon:body.polygon,edges:body.directionalSetbacks,edge_match_tolerance_m:Number(body?.edgeMatchToleranceM??1)}:{polygon:body.polygon,setback_m:numberValue(body?.setbackM??0,'setbackM')};const envelopeResponse=await fetch(`${base}${envelopePath}`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:json(envelopeInput)});const envelope=await envelopeResponse.json().catch(()=>({}));if(!envelopeResponse.ok)throw new HttpException(envelope?.detail||`aitec_envelope_${envelopeResponse.status}`,502);
      let parking:any=null;if(body?.requiredSpaces!=null){const p=await fetch(`${base}/aitec/v1/parking`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:json({required_spaces:Number(body.requiredSpaces),stall_width_m:body?.stallWidthM??2.5,stall_length_m:body?.stallLengthM??5,circulation_factor:body?.circulationFactor??1.65})});parking=await p.json().catch(()=>({}));if(!p.ok)throw new HttpException(parking?.detail||`aitec_parking_${p.status}`,502);}
      let massing:any=null;if(body?.caMax!=null&&envelope?.status==='CALCULATED'){const m=await fetch(`${base}/aitec/v1/massing`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:json({parcel_area_m2:envelope.parcel_area_m2,buildable_area_m2:envelope.buildable_area_m2,ca_max:Number(body.caMax),height_max_m:body?.heightMaxM??null,floor_height_m:body?.floorHeightM??3,efficiency:body?.efficiency??0.78})});massing=await m.json().catch(()=>({}));if(!m.ok)throw new HttpException(massing?.detail||`aitec_massing_${m.status}`,502);}
      let unitProgram:any=null;if(Array.isArray(body?.unitTypes)&&body.unitTypes.length){const u=await fetch(`${base}/aitec/v1/unit-program`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:json({unit_types:body.unitTypes})});unitProgram=await u.json().catch(()=>({}));if(!u.ok)throw new HttpException(unitProgram?.detail||`aitec_units_${u.status}`,502);}
      const hardConstraints=Array.isArray(body?.hardConstraints)?body.hardConstraints:[];let constraintId=body?.constraintSnapshotId||null;if(!constraintId){const cs=await c.query(`insert into aitec.constraint_snapshot(tenant_id,project_id,base_date,constraints,source_rule_ids) values($1,$2,$3,$4::jsonb,$5::uuid[]) returning id`,[s.organizationId,id,dateOnly(body?.baseDate),json({setbackM:body?.setbackM??0,directionalSetbacks:directional?body.directionalSetbacks:[],caMax:body?.caMax??null,heightMaxM:body?.heightMaxM??null,hard:hardConstraints}),Array.isArray(body?.sourceRuleIds)?body.sourceRuleIds:[]]);constraintId=cs.rows[0].id;}
      const metrics={parcel_area_m2:envelope.parcel_area_m2??null,buildable_area_m2:envelope.buildable_area_m2??null,parking_area_m2:parking?.estimated_total_area_m2??null,required_spaces:parking?.required_spaces??null,max_gross_floor_area_m2:massing?.max_gross_floor_area_m2??null,estimated_net_area_m2:massing?.estimated_net_area_m2??null,total_units:unitProgram?.total_units??null,estimated_floor_count:massing?.estimated_floor_count??null};
      let constraintValidation:any={status:'UNVERIFIED',reason:'envelope_not_calculated',results:[]};if(envelope?.status==='CALCULATED'){const vr=await fetch(`${base}/aitec/v1/validate-constraints`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:json({metrics,constraints:hardConstraints})});constraintValidation=await vr.json().catch(()=>({status:'UNVERIFIED',reason:'validator_invalid_response'}));if(!vr.ok)throw new HttpException(constraintValidation?.detail||`aitec_constraint_validator_${vr.status}`,502);}
      const scenarioStatus=envelope?.status!=='CALCULATED'?'INVALID_ENVELOPE':constraintValidation.status==='PASS'?'VALIDATED_PRELIMINARY':constraintValidation.status==='FAIL'?'INVALID_CONSTRAINTS':'PRELIMINARY_UNVERIFIED';
      const scenario=await c.query(`insert into aitec.scenario(tenant_id,project_id,constraint_snapshot_id,solver_version,status,metrics) values($1,$2,$3,$4,$5,$6::jsonb) returning id,status,metrics,created_at`,[s.organizationId,id,constraintId,PLATFORM_VERSION,scenarioStatus,json({...metrics,envelope,parking,massing,unitProgram,constraintValidation})]);
      for(const [code,value] of Object.entries(metrics)){if(value==null)continue;await c.query(`insert into aitec.scenario_metric(tenant_id,scenario_id,metric_code,value_numeric,unit) values($1,$2,$3,$4,$5) on conflict(scenario_id,metric_code) do update set value_numeric=excluded.value_numeric,unit=excluded.unit`,[s.organizationId,scenario.rows[0].id,code,Number(value),code.includes('area')?'m2':code.includes('spaces')||code.includes('units')?'count':null]);}
      if(unitProgram?.unit_types){await c.query(`delete from aitec.unit_program where project_id=$1 and tenant_id=$2`,[id,s.organizationId]);for(const item of unitProgram.unit_types)await c.query(`insert into aitec.unit_program(tenant_id,project_id,unit_type,target_area_m2,quantity,metadata) values($1,$2,$3,$4,$5,$6::jsonb)`,[s.organizationId,id,item.name,item.target_area_m2,item.quantity,json({total_private_area_m2:item.total_private_area_m2})]);}
      const result={scenario:scenario.rows[0],envelope,parking,massing,unitProgram,constraintValidation,limitations:[...(envelope.limitations||[]),...(parking?.limitations||[]),...(massing?.limitations||[]),...(constraintValidation.status==='UNVERIFIED'?['Cenário não recebe status de válido enquanto houver constraint dura ausente/não avaliada.']:[])]};
      await enqueueOutbox(c,'aitec.scenario.completed',{projectId:id,scenarioId:scenario.rows[0].id,status:scenario.rows[0].status,metrics},{tenantId:s.organizationId,aggregateType:'aitec.scenario',aggregateId:scenario.rows[0].id,dedupeKey:`aitec.scenario.completed:${scenario.rows[0].id}`});
      return result;
    });
    return{...idem.value,idempotency:{replayed:idem.replayed,key:key||null}};
  }
  @Post('aitec/projects/:id/solutions/generate')
  async generateAitecSolutions(@Req() req:any,@Param('id') id:string,@Body() body:any){
    const s=await this.moduleSession(req,'ai-tec');if(!body?.polygon)throw new HttpException('polygon é obrigatório',400);
    for(const [keyName,value] of Object.entries({caMax:body?.caMax,toMax:body?.toMax,tpMin:body?.tpMin,heightMaxM:body?.heightMaxM}))if(value==null)throw new HttpException(`${keyName} é obrigatório para o Site Solver`,400);
    const count=Math.max(1,Math.min(200,Number(body?.count??30)));const seed=Math.trunc(Number(body?.seed??1));
    const idemKey=String(req.headers?.['idempotency-key']||'').trim()||undefined;
    const idem=await withIdempotency(pool,s.organizationId,`aitec.site-solver:${id}:${seed}:${count}`,idemKey,async c=>{
      await c.query(`select set_config('app.tenant_id',$1,true)`,[s.organizationId]);
      const project=await c.query(`select id,parcel_id from aitec.project where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!project.rowCount)throw new HttpException('aitec_project_not_found',404);
      let constraintId=body?.constraintSnapshotId||null;
      if(constraintId){const exists=await c.query(`select id from aitec.constraint_snapshot where id=$1 and project_id=$2 and tenant_id=$3`,[constraintId,id,s.organizationId]);if(!exists.rowCount)throw new HttpException('constraint_snapshot_not_found',404);}
      if(!constraintId){
        const constraints={setbackM:Number(body?.setbackM??0),caMax:Number(body.caMax),toMax:Number(body.toMax),tpMin:Number(body.tpMin),heightMaxM:Number(body.heightMaxM),floorHeightM:Number(body?.floorHeightM??3),minSpacingM:Number(body?.minSpacingM??8),program:{avgUnitAreaM2:Number(body?.avgUnitAreaM2??65),spacesPerUnit:Number(body?.spacesPerUnit??1),requiredSpaces:body?.requiredSpaces??null,stallWidthM:Number(body?.stallWidthM??2.5),stallLengthM:Number(body?.stallLengthM??5.0),aisleWidthM:Number(body?.aisleWidthM??6.0),accessPoint:body?.accessPoint||null,accessRequired:Boolean(body?.accessRequired??false),roadWidthM:Number(body?.roadWidthM??6),unitMix:Array.isArray(body?.unitMix)?body.unitMix:[],minTotalUnits:body?.minTotalUnits??null,terrainSampleCount:Array.isArray(body?.terrainSamples)?body.terrainSamples.length:0,coreAreaM2:Number(body?.coreAreaM2??40),circulationWidthM:Number(body?.circulationWidthM??1.8)},source:'A.I TEC Site Solver v19-rc3'};
        const cs=await c.query(`insert into aitec.constraint_snapshot(tenant_id,project_id,parcel_id,base_date,constraints,source_rule_ids) values($1,$2,$3,$4,$5::jsonb,$6::uuid[]) returning id`,[s.organizationId,id,project.rows[0].parcel_id||null,dateOnly(body?.baseDate),json(constraints),Array.isArray(body?.sourceRuleIds)?body.sourceRuleIds:[]]);constraintId=cs.rows[0].id;
      }
      const base=process.env.AITEC_ENGINE_INTERNAL_URL||'http://aitec-engine:8002',token=process.env.INTERNAL_API_TOKEN||'';
      const input={polygon:body.polygon,setback_m:Number(body?.setbackM??0),ca_max:Number(body.caMax),to_max:Number(body.toMax),tp_min:Number(body.tpMin),height_max_m:Number(body.heightMaxM),floor_height_m:Number(body?.floorHeightM??3),efficiency:Number(body?.efficiency??0.78),avg_unit_area_m2:Number(body?.avgUnitAreaM2??65),min_buildings:Number(body?.minBuildings??1),max_buildings:Number(body?.maxBuildings??4),min_spacing_m:Number(body?.minSpacingM??8),spaces_per_unit:Number(body?.spacesPerUnit??1),required_spaces:body?.requiredSpaces==null?null:Number(body.requiredSpaces),stall_width_m:Number(body?.stallWidthM??2.5),stall_length_m:Number(body?.stallLengthM??5.0),aisle_width_m:Number(body?.aisleWidthM??6.0),access_point:body?.accessPoint||null,access_required:Boolean(body?.accessRequired??false),road_width_m:Number(body?.roadWidthM??6.0),unit_mix:Array.isArray(body?.unitMix)?body.unitMix:[],min_total_units:body?.minTotalUnits==null?null:Number(body.minTotalUnits),terrain_samples:Array.isArray(body?.terrainSamples)?body.terrainSamples:[],core_area_m2:Number(body?.coreAreaM2??40),circulation_width_m:Number(body?.circulationWidthM??1.8),locked_footprints:Array.isArray(body?.lockedFootprints)?body.lockedFootprints:[],count,seed};
      const response=await fetch(`${base}/aitec/v1/site-solver`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:json(input)});const output=await response.json().catch(()=>({}));if(!response.ok)throw new HttpException(output?.detail||`aitec_site_solver_${response.status}`,502);
      if(output?.status!=='GENERATED'||!Array.isArray(output?.items))return{...output,persisted:0,constraintSnapshotId:constraintId};
      const pareto=new Set(Array.isArray(output?.pareto_ids)?output.pareto_ids:[]);const saved=[] as any[];
      for(const item of output.items){
        const hardInvalid=Boolean(item?.hard_invalid)||item?.validation?.status!=='PASS';const status=hardInvalid?'INVALID_CONSTRAINTS':'VALIDATED_PRELIMINARY';
        const row=await c.query(`insert into aitec.solution(tenant_id,project_id,constraint_snapshot_id,solver_version,seed,variation_index,status,objectives,metrics,validation,assumptions,is_pareto,pareto_rank) values($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10::jsonb,$11::jsonb,$12,$13) on conflict(project_id,solver_version,seed,variation_index) do update set status=excluded.status,objectives=excluded.objectives,metrics=excluded.metrics,validation=excluded.validation,assumptions=excluded.assumptions,is_pareto=excluded.is_pareto,pareto_rank=excluded.pareto_rank returning id,status,is_pareto,metrics,validation,variation_index`,[s.organizationId,id,constraintId,String(output.solver_version||'site-solver-rc3'),seed,Number(item?.variation??0),status,json(body?.objectives||{estimated_net_area_m2:'MAX',tp_achieved:'MAX',parking_area_m2:'MIN'}),json(item?.metrics||{}),json(item?.validation||{}),json({input,projection:output?.projection,limitations:[...(output?.limitations||[]),...(item?.limitations||[])]}),pareto.has(item?.id),pareto.has(item?.id)?1:null]);
        const solutionId=row.rows[0].id;await c.query(`delete from aitec.geometry_object where solution_id=$1 and tenant_id=$2`,[solutionId,s.organizationId]);
        const features=Array.isArray(item?.geometry?.features)?item.geometry.features:[];for(const feature of features){if(!feature?.geometry)continue;await c.query(`insert into aitec.geometry_object(tenant_id,solution_id,object_type,ordinal,geom,properties,lineage) values($1,$2,$3,$4,ST_SetSRID(ST_GeomFromGeoJSON($5),4326),$6::jsonb,$7::jsonb)`,[s.organizationId,solutionId,String(feature?.properties?.objectType||'BUILDING_FOOTPRINT'),Number(feature?.properties?.ordinal??0),json(feature.geometry),json(feature.properties||{}),json({solverVersion:output?.solver_version,seed,variation:item?.variation,constraintSnapshotId:constraintId})]);}
        await c.query(`delete from aitec.violation where solution_id=$1 and tenant_id=$2`,[solutionId,s.organizationId]);for(const check of (item?.validation?.results||[])){if(check?.status==='PASS')continue;await c.query(`insert into aitec.violation(tenant_id,solution_id,constraint_code,status,severity,observed,expected,evidence,explanation) values($1,$2,$3,$4,'HARD',$5::jsonb,$6::jsonb,$7::jsonb,$8)`,[s.organizationId,solutionId,String(check?.code||check?.metric||'UNKNOWN'),String(check?.status||'UNEVALUATED'),json({metric:check?.metric,value:check?.observed}),json(check?.expected||{}),json({sourceRuleIds:Array.isArray(body?.sourceRuleIds)?body.sourceRuleIds:[],constraintSnapshotId:constraintId}),String(check?.reason||'Restrição dura não satisfeita ou não avaliada.')]);}
        for(const a of [{type:'TERRAIN_CUT_FILL',data:item?.terrain,method:'explicit_xyz_median_pad'},{type:'BUILDING_STACK',data:item?.building,method:'conceptual_core_circulation'}]){if(!a.data||a.data.status==='NOT_PROVIDED')continue;await c.query(`delete from aitec.analysis_result where solution_id=$1 and tenant_id=$2 and analysis_type=$3`,[solutionId,s.organizationId,a.type]);await c.query(`insert into aitec.analysis_result(tenant_id,solution_id,analysis_type,method,method_version,input_snapshot,output_snapshot,confidence_status) values($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8)`,[s.organizationId,solutionId,a.type,a.method,String(output?.solver_version||'site-solver-rc3'),json({constraintSnapshotId:constraintId,seed,variation:item?.variation}),json(a.data),String(a.data.status||'PRELIMINARY')]);}
        saved.push({...row.rows[0],localSolutionId:item?.id});
      }
      await enqueueOutbox(c,'aitec.solutions.generated',{projectId:id,constraintSnapshotId:constraintId,solverVersion:output?.solver_version,seed,requested:count,persisted:saved.length,hardValid:output?.hard_valid_count,pareto:saved.filter(x=>x.is_pareto).map(x=>x.id)},{tenantId:s.organizationId,aggregateType:'aitec.project',aggregateId:id,dedupeKey:`aitec.solutions.generated:${id}:${constraintId}:${seed}:${count}`});
      return{status:output.status,solverVersion:output.solver_version,seed,requestedCount:output.requested_count,generatedCount:output.generated_count,hardValidCount:output.hard_valid_count,constraintSnapshotId:constraintId,envelope:output.envelope,solutions:saved,limitations:output.limitations||[]};
    });return{...idem.value,idempotency:{replayed:idem.replayed,key:idemKey||null}};
  }

  @Get('aitec/projects/:id/solutions')
  async listAitecSolutions(@Req() req:any,@Param('id') id:string,@Query('pareto') paretoRaw?:string){
    const s=await this.moduleSession(req,'ai-tec');const onlyPareto=String(paretoRaw||'').toLowerCase()==='true';return tenantTransaction(s.organizationId,async c=>{const p=await c.query(`select id from aitec.project where id=$1 and tenant_id=$2`,[id,s.organizationId]);if(!p.rowCount)throw new HttpException('aitec_project_not_found',404);const r=await c.query(`select s.id,s.constraint_snapshot_id,s.parent_solution_id,s.solver_version,s.seed,s.variation_index,s.status,s.objectives,s.metrics,s.validation,s.is_pareto,s.pareto_rank,s.generated_at,(select count(*)::int from aitec.geometry_object g where g.solution_id=s.id and g.tenant_id=$2) geometry_objects,(select count(*)::int from aitec.violation v where v.solution_id=s.id and v.tenant_id=$2 and v.status<>'PASS') violations from aitec.solution s where s.project_id=$1 and s.tenant_id=$2 and ($3::boolean=false or s.is_pareto) order by s.is_pareto desc,s.pareto_rank nulls last,s.generated_at desc limit 200`,[id,s.organizationId,onlyPareto]);return{items:r.rows};});
  }

  @Get('aitec/solutions/:solutionId')
  async getAitecSolution(@Req() req:any,@Param('solutionId') solutionId:string){
    const s=await this.moduleSession(req,'ai-tec');return tenantTransaction(s.organizationId,async c=>{const r=await c.query(`select * from aitec.solution where id=$1 and tenant_id=$2`,[solutionId,s.organizationId]);if(!r.rowCount)throw new HttpException('aitec_solution_not_found',404);const [objects,violations,locks,analyses,artifacts]=await Promise.all([c.query(`select id,object_type,ordinal,ST_AsGeoJSON(geom)::json geometry,properties,lineage from aitec.geometry_object where solution_id=$1 and tenant_id=$2 order by object_type,ordinal`,[solutionId,s.organizationId]),c.query(`select constraint_code,status,severity,observed,expected,evidence,explanation from aitec.violation where solution_id=$1 and tenant_id=$2 order by created_at`,[solutionId,s.organizationId]),c.query(`select id,geometry_object_id,lock_code,payload,created_by,created_at from aitec.solution_lock where solution_id=$1 and tenant_id=$2 order by created_at`,[solutionId,s.organizationId]),c.query(`select id,analysis_type,method,method_version,input_snapshot,output_snapshot,confidence_status,created_at from aitec.analysis_result where solution_id=$1 and tenant_id=$2 order by created_at desc`,[solutionId,s.organizationId]),c.query(`select id,kind,object_key,content_type,sha256,metadata,created_at from aitec.artifact where solution_id=$1 and tenant_id=$2 order by created_at desc`,[solutionId,s.organizationId])]);return{solution:r.rows[0],geometryObjects:objects.rows,violations:violations.rows,locks:locks.rows,analyses:analyses.rows,artifacts:artifacts.rows};});
  }


  @Post('aitec/solutions/:solutionId/locks')
  async lockAitecSolution(@Req() req:any,@Param('solutionId') solutionId:string,@Body() body:any){
    const s=await this.moduleSession(req,'ai-tec');const ids=Array.isArray(body?.geometryObjectIds)?body.geometryObjectIds.map(String):[];if(!ids.length)throw new HttpException('geometryObjectIds obrigatório',400);const lockCode=String(body?.lockCode||'GEOMETRY').toUpperCase();return tenantTransaction(s.organizationId,async c=>{const sol=await c.query(`select id from aitec.solution where id=$1 and tenant_id=$2`,[solutionId,s.organizationId]);if(!sol.rowCount)throw new HttpException('aitec_solution_not_found',404);if(body?.clearExisting===true)await c.query(`delete from aitec.solution_lock where solution_id=$1 and tenant_id=$2 and lock_code=$3`,[solutionId,s.organizationId,lockCode]);const saved=[];for(const objectId of ids){const obj=await c.query(`select id,object_type,ordinal from aitec.geometry_object where id=$1 and solution_id=$2 and tenant_id=$3`,[objectId,solutionId,s.organizationId]);if(!obj.rowCount)throw new HttpException(`geometry_object_not_found:${objectId}`,404);const r=await c.query(`insert into aitec.solution_lock(tenant_id,solution_id,geometry_object_id,lock_code,payload,created_by) values($1,$2,$3,$4,$5::jsonb,$6) on conflict(solution_id,geometry_object_id,lock_code) do update set payload=excluded.payload,created_by=excluded.created_by,created_at=now() returning id,geometry_object_id,lock_code,payload,created_by,created_at`,[s.organizationId,solutionId,objectId,lockCode,json({objectType:obj.rows[0].object_type,ordinal:obj.rows[0].ordinal,...(body?.payload||{})}),s.email||s.id||null]);saved.push(r.rows[0]);}await enqueueOutbox(c,'aitec.solution.locks.updated',{solutionId,lockCode,count:saved.length},{tenantId:s.organizationId,aggregateType:'aitec.solution',aggregateId:solutionId,dedupeKey:`aitec.solution.locks.updated:${solutionId}:${lockCode}:${saved.map(x=>x.geometry_object_id).sort().join(',')}`});return{solutionId,lockCode,items:saved};});
  }

  @Post('aitec/solutions/:solutionId/branch')
  async branchAitecSolution(@Req() req:any,@Param('solutionId') solutionId:string,@Body() body:any){
    const s=await this.moduleSession(req,'ai-tec');const parent=await tenantTransaction(s.organizationId,async c=>{const r=await c.query(`select id,project_id,seed,solver_version,assumptions from aitec.solution where id=$1 and tenant_id=$2`,[solutionId,s.organizationId]);if(!r.rowCount)throw new HttpException('aitec_solution_not_found',404);const locks=await c.query(`select g.id,g.object_type,ST_AsGeoJSON(g.geom)::json geometry from aitec.solution_lock l join aitec.geometry_object g on g.id=l.geometry_object_id and g.tenant_id=l.tenant_id where l.solution_id=$1 and l.tenant_id=$2 and l.lock_code='GEOMETRY' and g.object_type='BUILDING_FOOTPRINT' order by g.ordinal`,[solutionId,s.organizationId]);return{...r.rows[0],lockedFootprints:locks.rows.map((x:any)=>x.geometry)};});const i=parent.assumptions?.input||{};const branchBody={polygon:i.polygon,setbackM:i.setback_m,caMax:i.ca_max,toMax:i.to_max,tpMin:i.tp_min,heightMaxM:i.height_max_m,floorHeightM:i.floor_height_m,efficiency:i.efficiency,avgUnitAreaM2:i.avg_unit_area_m2,minBuildings:Math.max(Number(i.min_buildings||1),parent.lockedFootprints.length||1),maxBuildings:Math.max(Number(i.max_buildings||4),parent.lockedFootprints.length||1),minSpacingM:i.min_spacing_m,spacesPerUnit:i.spaces_per_unit,requiredSpaces:i.required_spaces,stallWidthM:i.stall_width_m,stallLengthM:i.stall_length_m,aisleWidthM:i.aisle_width_m,accessPoint:i.access_point,accessRequired:i.access_required,roadWidthM:i.road_width_m,unitMix:i.unit_mix,minTotalUnits:i.min_total_units,terrainSamples:Array.isArray(body?.terrainSamples)?body.terrainSamples:(Array.isArray(i.terrain_samples)?i.terrain_samples:[]),coreAreaM2:i.core_area_m2,circulationWidthM:i.circulation_width_m,lockedFootprints:parent.lockedFootprints,count:Number(body?.count??20),seed:Number(body?.seed??(Number(parent.seed)+1)),baseDate:body?.baseDate||new Date().toISOString().slice(0,10),constraintSnapshotId:body?.constraintSnapshotId||null,objectives:body?.objectives||{estimated_net_area_m2:'MAX',tp_achieved:'MAX',parking_area_m2:'MIN'}};if(!branchBody.polygon)throw new HttpException('parent_solution_has_no_reproducible_input',409);const generated:any=await this.generateAitecSolutions(req,parent.project_id,branchBody);const childIds=(generated?.solutions||[]).map((x:any)=>x.id).filter(Boolean);if(childIds.length)await tenantTransaction(s.organizationId,async c=>{await c.query(`update aitec.solution set parent_solution_id=$1 where tenant_id=$2 and id=any($3::uuid[])`,[solutionId,s.organizationId,childIds]);await enqueueOutbox(c,'aitec.solution.branched',{parentSolutionId:solutionId,childSolutionIds:childIds,lockedBuildings:parent.lockedFootprints.length,seed:branchBody.seed},{tenantId:s.organizationId,aggregateType:'aitec.solution',aggregateId:solutionId,dedupeKey:`aitec.solution.branched:${solutionId}:${branchBody.seed}:${childIds.join(',')}`});});return{...generated,parentSolutionId:solutionId,lockedBuildingCount:parent.lockedFootprints.length,childSolutionIds:childIds};
  }

  @Post('aitec/solutions/:solutionId/export-geojson')
  async exportAitecSolutionGeojson(@Req() req:any,@Param('solutionId') solutionId:string){
    const s=await this.moduleSession(req,'ai-tec');return tenantTransaction(s.organizationId,async c=>{const sol=await c.query(`select id,project_id,status,solver_version,seed,variation_index,metrics,validation from aitec.solution where id=$1 and tenant_id=$2`,[solutionId,s.organizationId]);if(!sol.rowCount)throw new HttpException('aitec_solution_not_found',404);const objects=await c.query(`select id,object_type,ordinal,ST_AsGeoJSON(geom)::json geometry,properties,lineage from aitec.geometry_object where solution_id=$1 and tenant_id=$2 order by object_type,ordinal`,[solutionId,s.organizationId]);const payload={type:'FeatureCollection',features:objects.rows.map((x:any)=>({type:'Feature',id:x.id,geometry:x.geometry,properties:{...x.properties,objectType:x.object_type,ordinal:x.ordinal,lineage:x.lineage,solutionId}})),metadata:{solutionId,projectId:sol.rows[0].project_id,status:sol.rows[0].status,solverVersion:sol.rows[0].solver_version,seed:sol.rows[0].seed,variationIndex:sol.rows[0].variation_index,metrics:sol.rows[0].metrics,validation:sol.rows[0].validation,generatedBy:`LoteDiretor A.I TEC ${PLATFORM_VERSION}`,maturity:'PRELIMINARY_NOT_EXECUTIVE'}};const raw=Buffer.from(JSON.stringify(payload));const sha=createHash('sha256').update(raw).digest('hex');const key=`tenant/${s.organizationId}/aitec/${sol.rows[0].project_id}/solutions/${solutionId}/${randomUUID()}.geojson`;await s3.send(new PutObjectCommand({Bucket:S3_BUCKET,Key:key,Body:raw,ContentType:'application/geo+json',Metadata:{sha256:sha,solution:solutionId}}));const a=await c.query(`insert into aitec.artifact(tenant_id,scenario_id,solution_id,kind,object_key,content_type,sha256,metadata) values($1,null,$2,'GEOJSON',$3,'application/geo+json',$4,$5::jsonb) returning id,kind,object_key,content_type,sha256,created_at`,[s.organizationId,solutionId,key,sha,json({preliminary:true,projectId:sol.rows[0].project_id,solverVersion:sol.rows[0].solver_version})]);return a.rows[0];});
  }

  @Post('aitec/solutions/:solutionId/export-csv')
  async exportAitecSolutionCsv(@Req() req:any,@Param('solutionId') solutionId:string){
    const s=await this.moduleSession(req,'ai-tec');return tenantTransaction(s.organizationId,async c=>{const sol=await c.query(`select id,project_id,status,solver_version,seed,variation_index,metrics from aitec.solution where id=$1 and tenant_id=$2`,[solutionId,s.organizationId]);if(!sol.rowCount)throw new HttpException('aitec_solution_not_found',404);const counts=await c.query(`select object_type,count(*)::int n from aitec.geometry_object where solution_id=$1 and tenant_id=$2 group by object_type order by object_type`,[solutionId,s.organizationId]);const esc=(v:any)=>`"${String(v??'').replace(/"/g,'""')}"`;const lines=[['section','code','value'].map(esc).join(',')];for(const [k,v] of Object.entries(sol.rows[0].metrics||{}))lines.push(['metric',k,typeof v==='object'?JSON.stringify(v):v].map(esc).join(','));for(const row of counts.rows)lines.push(['geometry_count',row.object_type,row.n].map(esc).join(','));lines.push(['metadata','solver_version',sol.rows[0].solver_version].map(esc).join(','),['metadata','seed',sol.rows[0].seed].map(esc).join(','),['metadata','variation_index',sol.rows[0].variation_index].map(esc).join(','),['metadata','status',sol.rows[0].status].map(esc).join(','));const raw=Buffer.from(lines.join('\n')+'\n');const sha=createHash('sha256').update(raw).digest('hex');const key=`tenant/${s.organizationId}/aitec/${sol.rows[0].project_id}/solutions/${solutionId}/${randomUUID()}.csv`;await s3.send(new PutObjectCommand({Bucket:S3_BUCKET,Key:key,Body:raw,ContentType:'text/csv; charset=utf-8',Metadata:{sha256:sha,solution:solutionId}}));const a=await c.query(`insert into aitec.artifact(tenant_id,scenario_id,solution_id,kind,object_key,content_type,sha256,metadata) values($1,null,$2,'CSV',$3,'text/csv; charset=utf-8',$4,$5::jsonb) returning id,kind,object_key,content_type,sha256,created_at`,[s.organizationId,solutionId,key,sha,json({preliminary:true,projectId:sol.rows[0].project_id})]);return a.rows[0];});
  }

  @Post('aitec/projects/:id/scenarios/rank')
  async rankAitecScenarios(@Req() req:any,@Param('id') id:string,@Body() body:any){
    const s=await this.moduleSession(req,'ai-tec');const rows=await tenantTransaction(s.organizationId,async c=>(await c.query(`select id,status,metrics from aitec.scenario where project_id=$1 and tenant_id=$2 order by created_at desc limit 100`,[id,s.organizationId])).rows);if(!rows.length)return{status:'NO_SCENARIOS',items:[]};
    const base=process.env.AITEC_ENGINE_INTERNAL_URL||'http://aitec-engine:8002';const token=process.env.INTERNAL_API_TOKEN||'';const scenarios=rows.map((x:any)=>({id:x.id,hard_invalid:String(x.status)!=='VALIDATED_PRELIMINARY',metrics:{buildable_area_m2:Number(x.metrics?.buildable_area_m2||0),max_gross_floor_area_m2:Number(x.metrics?.max_gross_floor_area_m2||0),estimated_net_area_m2:Number(x.metrics?.estimated_net_area_m2||0),total_units:Number(x.metrics?.total_units||0),parking_area_m2:Number(x.metrics?.parking_area_m2||0)}}));const weights=body?.weights||{estimated_net_area_m2:0.5,total_units:0.3,buildable_area_m2:0.2};const r=await fetch(`${base}/aitec/v1/pareto`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:json({scenarios,weights})});const out=await r.json().catch(()=>({}));if(!r.ok)throw new HttpException(out?.detail||`aitec_pareto_${r.status}`,502);return out;
  }

  @Post('aitec/projects/:id/scenarios/:scenarioId/export-geojson')
  async exportAitecGeojson(@Req() req:any,@Param('id') id:string,@Param('scenarioId') scenarioId:string){
    const s=await this.moduleSession(req,'ai-tec');return tenantTransaction(s.organizationId,async c=>{const row=await c.query(`select s.id,s.metrics,p.name project_name from aitec.scenario s join aitec.project p on p.id=s.project_id where s.id=$1 and s.project_id=$2 and s.tenant_id=$3`,[scenarioId,id,s.organizationId]);if(!row.rowCount)throw new HttpException('scenario_not_found',404);const envelope=row.rows[0].metrics?.envelope;const geometry=envelope?.geometry;if(!geometry)throw new HttpException('scenario_has_no_exportable_geometry',409);const payload={type:'FeatureCollection',features:[{type:'Feature',id:scenarioId,geometry,properties:{projectId:id,projectName:row.rows[0].project_name,scenarioId,status:'PRELIMINARY',generatedBy:`LoteDiretor A.I TEC ${PLATFORM_VERSION}`}}]};const raw=Buffer.from(JSON.stringify(payload));const sha=createHash('sha256').update(raw).digest('hex');const key=`tenant/${s.organizationId}/aitec/${id}/${scenarioId}/${randomUUID()}.geojson`;await s3.send(new PutObjectCommand({Bucket:S3_BUCKET,Key:key,Body:raw,ContentType:'application/geo+json',Metadata:{sha256:sha,scenario:scenarioId}}));const a=await c.query(`insert into aitec.artifact(tenant_id,scenario_id,kind,object_key,content_type,sha256,metadata) values($1,$2,'GEOJSON',$3,'application/geo+json',$4,$5::jsonb) returning id,kind,object_key,content_type,sha256,created_at`,[s.organizationId,scenarioId,key,sha,json({preliminary:true,projectId:id})]);return a.rows[0];});
  }

  @Get('reports/:id')
  async reportStatus(@Req() req:any,@Param('id') id:string){const s=await this.moduleSession(req,'relatorios');return tenantTransaction(s.organizationId,async c=>{const r=await c.query(`select rr.id,rr.kind,rr.subject_type,rr.subject_id,rr.base_date,rr.status,rr.template_code,rr.template_version,rr.renderer_version,rr.confidence_summary,rr.metadata,rr.artifact_key,rr.sha256,rr.frozen_at,rr.created_at,rr.completed_at,ra.object_key artifact_object_key,ra.content_type,ra.size_bytes,ra.sha256 artifact_sha256 from report.report_run rr left join report.artifact ra on ra.report_run_id=rr.id where rr.id=$1 and rr.tenant_id=$2`,[id,s.organizationId]);if(!r.rowCount)throw new HttpException('report_not_found',404);return r.rows[0];});}

  @Get('notifications')
  async notifications(@Req() req:any,@Query('status') status?:string){const s=await this.session(req);return tenantTransaction(s.organizationId,async c=>({items:(await c.query(`select id,kind,title,body,status,payload,created_at,read_at from notification.notification where tenant_id=$1 and ($2::text is null or status=$2) order by created_at desc limit 100`,[s.organizationId,status||null])).rows}));}

  @Post('notifications/:id/read')
  async readNotification(@Req() req:any,@Param('id') id:string){const s=await this.session(req);return tenantTransaction(s.organizationId,async c=>{const r=await c.query(`update notification.notification set status='READ',read_at=coalesce(read_at,now()) where id=$1 and tenant_id=$2 returning *`,[id,s.organizationId]);if(!r.rowCount)throw new HttpException('notification_not_found',404);return r.rows[0];});}
}
