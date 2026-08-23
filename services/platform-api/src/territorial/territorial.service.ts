import {HttpException,Injectable} from '@nestjs/common';
import {Pool,PoolClient} from 'pg';
import {tenantTx} from '../common/tenant-db';
import {evaluateRuleCondition,normalizeRuleNumber,RuleContext} from './rule-evaluator';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});

export type ResolverInput={
  point?:{lat:number;lon:number};
  polygon?:any;
  address?:string;
  municipalityIbge?:string;
  identifier?:{type:'CIB'|'MUNICIPAL_REGISTRATION'|'MATRICULA_REFERENCE'|'OFFICIAL_PARCEL_ID'|string;value:string};
};

function cleanDate(value?:string){
  if(!value)return new Date().toISOString().slice(0,10);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value))throw new HttpException('baseDate deve usar YYYY-MM-DD',400);
  return value;
}
function normalizeAddress(value:string){return value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();}
function num(value:any,name:string){const n=Number(value);if(!Number.isFinite(n))throw new HttpException(`${name} inválido`,400);return n;}
function geojson(value:any){try{return JSON.stringify(value)}catch{throw new HttpException('GeoJSON inválido',400)}}

function cleanRuleContext(raw:any):Partial<RuleContext>{
  if(raw==null)return{};if(typeof raw!=='object'||Array.isArray(raw))throw new HttpException('context deve ser objeto',400);
  const out:Partial<RuleContext>={};
  const numeric:[keyof RuleContext,string][]=[['frontage_m','frontage_m'],['road_width_m','road_width_m'],['existing_floors','existing_floors'],['height_m','height_m']];
  for(const [key,label] of numeric){if(raw[key]!==undefined&&raw[key]!==null&&raw[key]!==''){const v=Number(raw[key]);if(!Number.isFinite(v)||v<0)throw new HttpException(`${label} inválido`,400);(out as any)[key]=v;}}
  if(raw.corner_lot!==undefined){if(typeof raw.corner_lot!=='boolean')throw new HttpException('corner_lot deve ser boolean',400);out.corner_lot=raw.corner_lot;}
  if(raw.proposed_use!==undefined&&raw.proposed_use!==null){const v=String(raw.proposed_use).trim();if(!v)throw new HttpException('proposed_use inválido',400);out.proposed_use=v.slice(0,120);}
  return out;
}

@Injectable()
export class TerritorialService{
  readonly pool=pool;

  baseDate(value?:string){return cleanDate(value)}

  async resolve(tenantId:string,input:ResolverInput,baseDate?:string){
    const at=cleanDate(baseDate);
    return tenantTx(pool,tenantId,c=>this.resolveWithClient(c,input,at));
  }

  async resolveWithClient(c:PoolClient,input:ResolverInput,at:string){
    const keys=['point','polygon','address','identifier'].filter(k=>(input as any)?.[k]!=null);
    if(keys.length!==1)throw new HttpException('Informe exatamente uma entrada: point, polygon, address ou identifier',400);
    const timestamp=`${at}T12:00:00Z`;
    let rows:any[]=[];let municipality:any=null;let inputEcho:any={};

    if(input.point){
      const lat=num(input.point.lat,'lat'),lon=num(input.point.lon,'lon');
      if(lat<-90||lat>90||lon<-180||lon>180)throw new HttpException('coordenadas fora do intervalo',400);
      inputEcho={kind:'POINT',lat,lon};
      const result=await c.query(`
        with q as (select st_setsrid(st_point($1,$2),4326) geom), exact as (
          select p.id,p.municipality_ibge,p.official_identifier,p.source_snapshot_id,
            st_area(p.geom::geography) area_m2,st_asgeojson(p.geom)::jsonb geometry,
            1.0::numeric confidence,'POINT_COVERED'::text reason,0::numeric distance_m
          from geo.parcel p,q
          where st_covers(p.geom,q.geom)
            and (p.valid_from is null or p.valid_from <= $3::timestamptz)
            and (p.valid_to is null or p.valid_to > $3::timestamptz)
            and (p.superseded_at is null or p.superseded_at > $3::timestamptz)
          order by p.recorded_at desc limit 10
        ), nearby as (
          select p.id,p.municipality_ibge,p.official_identifier,p.source_snapshot_id,
            st_area(p.geom::geography) area_m2,st_asgeojson(p.geom)::jsonb geometry,
            greatest(0.25,1-(st_distance(p.geom::geography,q.geom::geography)/50.0))::numeric confidence,
            'NEAREST_WITHIN_50M'::text reason,st_distance(p.geom::geography,q.geom::geography)::numeric distance_m
          from geo.parcel p,q
          where not exists(select 1 from exact)
            and st_dwithin(p.geom::geography,q.geom::geography,50)
            and (p.valid_from is null or p.valid_from <= $3::timestamptz)
            and (p.valid_to is null or p.valid_to > $3::timestamptz)
            and (p.superseded_at is null or p.superseded_at > $3::timestamptz)
          order by st_distance(p.geom::geography,q.geom::geography),p.recorded_at desc limit 10
        ) select * from exact union all select * from nearby order by confidence desc,distance_m asc nulls first limit 10`,[lon,lat,timestamp]);
      rows=result.rows;
      const mb=await c.query(`select b.municipality_ibge,m.name,m.uf from geo.municipality_boundary b join core.municipality m on m.ibge_code=b.municipality_ibge where st_covers(b.geom,st_setsrid(st_point($1,$2),4326)) and (b.valid_from is null or b.valid_from <= $3::timestamptz) and (b.valid_to is null or b.valid_to > $3::timestamptz) order by b.recorded_at desc limit 1`,[lon,lat,timestamp]);
      municipality=mb.rows[0]||null;
    }

    if(input.polygon){
      const raw=geojson(input.polygon);inputEcho={kind:'POLYGON'};
      const result=await c.query(`
        with q as (select st_multi(st_collectionextract(st_makevalid(st_setsrid(st_geomfromgeojson($1),4326)),3)) geom), candidates as (
          select p.id,p.municipality_ibge,p.official_identifier,p.source_snapshot_id,
            st_area(p.geom::geography) area_m2,st_asgeojson(p.geom)::jsonb geometry,
            st_area(st_intersection(p.geom,q.geom)::geography) overlap_area_m2,
            case when st_area(q.geom::geography)>0 then st_area(st_intersection(p.geom,q.geom)::geography)/st_area(q.geom::geography) else 0 end overlap_ratio
          from geo.parcel p,q where st_intersects(p.geom,q.geom)
            and (p.valid_from is null or p.valid_from <= $2::timestamptz)
            and (p.valid_to is null or p.valid_to > $2::timestamptz)
            and (p.superseded_at is null or p.superseded_at > $2::timestamptz)
        ) select *,least(1.0,greatest(0.1,overlap_ratio))::numeric confidence,'POLYGON_OVERLAP'::text reason,0::numeric distance_m from candidates order by overlap_ratio desc,overlap_area_m2 desc limit 10`,[raw,timestamp]);
      rows=result.rows;
      const mb=await c.query(`with q as (select st_pointonsurface(st_setsrid(st_geomfromgeojson($1),4326)) geom) select b.municipality_ibge,m.name,m.uf from geo.municipality_boundary b,q join core.municipality m on m.ibge_code=b.municipality_ibge where st_covers(b.geom,q.geom) order by b.recorded_at desc limit 1`,[raw]);
      municipality=mb.rows[0]||null;
    }

    if(input.address){
      const query=normalizeAddress(String(input.address));if(query.length<5)throw new HttpException('address muito curto',400);
      inputEcho={kind:'ADDRESS',address:String(input.address)};
      const result=await c.query(`select ai.id address_id,ai.formatted_address,ai.municipality_ibge,ai.parcel_id,
        similarity(ai.normalized_address,$1) address_score,st_y(ai.geom) lat,st_x(ai.geom) lon,
        p.id,p.official_identifier,p.source_snapshot_id,case when p.geom is null then null else st_area(p.geom::geography) end area_m2,
        case when p.geom is null then null else st_asgeojson(p.geom)::jsonb end geometry,
        greatest(0.1,similarity(ai.normalized_address,$1))::numeric confidence,'ADDRESS_INDEX'::text reason,0::numeric distance_m
        from geo.address_index ai left join geo.parcel p on p.id=ai.parcel_id
        where ai.normalized_address % $1 and ($2::text is null or ai.municipality_ibge=$2)
          and (ai.valid_from is null or ai.valid_from <= $3::timestamptz) and (ai.valid_to is null or ai.valid_to > $3::timestamptz)
        order by similarity(ai.normalized_address,$1) desc limit 10`,[query,input.municipalityIbge||null,timestamp]);
      rows=result.rows;
      if(rows[0]?.municipality_ibge){const m=await c.query(`select ibge_code municipality_ibge,name,uf from core.municipality where ibge_code=$1`,[rows[0].municipality_ibge]);municipality=m.rows[0]||null;}
    }

    if(input.identifier){
      const type=String(input.identifier.type||'').trim().toUpperCase(),value=String(input.identifier.value||'').trim();
      if(!type||!value)throw new HttpException('identifier.type e identifier.value são obrigatórios',400);
      inputEcho={kind:'IDENTIFIER',identifierType:type,identifierValue:value};
      if(type==='OFFICIAL_PARCEL_ID'){
        const result=await c.query(`select p.id,p.municipality_ibge,p.official_identifier,p.source_snapshot_id,st_area(p.geom::geography) area_m2,st_asgeojson(p.geom)::jsonb geometry,1.0::numeric confidence,'OFFICIAL_PARCEL_ID'::text reason,0::numeric distance_m from geo.parcel p where p.official_identifier=$1 and ($2::text is null or p.municipality_ibge=$2) and (p.valid_from is null or p.valid_from <= $3::timestamptz) and (p.valid_to is null or p.valid_to > $3::timestamptz) order by p.recorded_at desc limit 10`,[value,input.municipalityIbge||null,timestamp]);rows=result.rows;
      }else{
        const result=await c.query(`select p.id,p.municipality_ibge,p.official_identifier,p.source_snapshot_id,st_area(p.geom::geography) area_m2,st_asgeojson(p.geom)::jsonb geometry,1.0::numeric confidence,'ASSET_IDENTIFIER'::text reason,0::numeric distance_m,ai.identifier_type,ai.authority from core.asset_identifier ai join core.asset a on a.id=ai.asset_id join geo.parcel p on p.id=a.parcel_id where true and upper(ai.identifier_type)=$1 and ai.identifier_value=$2 and ($3::text is null or a.municipality_ibge=$3) and (ai.valid_from is null or ai.valid_from <= $4::timestamptz) and (ai.valid_to is null or ai.valid_to > $4::timestamptz) order by ai.created_at desc limit 10`,[type,value,input.municipalityIbge||null,timestamp]);rows=result.rows;
      }
      if(rows[0]?.municipality_ibge){const m=await c.query(`select ibge_code municipality_ibge,name,uf from core.municipality where ibge_code=$1`,[rows[0].municipality_ibge]);municipality=m.rows[0]||null;}
    }

    const candidates=[] as any[];
    for(const row of rows){
      const zones=await c.query(`select id,code,name,source_snapshot_id,valid_from,valid_to from planning.zone where municipality_ibge=$1 and $2::uuid is not null and st_intersects(geom,(select geom from geo.parcel where id=$2)) and (valid_from is null or valid_from <= $3::timestamptz) and (valid_to is null or valid_to > $3::timestamptz) order by valid_from desc nulls last,code limit 20`,[row.municipality_ibge,row.id||null,timestamp]);
      candidates.push({...row,confidence:Number(row.confidence??0),zones:zones.rows});
    }
    if(!municipality&&candidates[0]?.municipality_ibge){const m=await c.query(`select ibge_code municipality_ibge,name,uf from core.municipality where ibge_code=$1`,[candidates[0].municipality_ibge]);municipality=m.rows[0]||null;}
    return{status:candidates.length?'RESOLVED':'NOT_FOUND',baseDate:at,input:inputEcho,municipality,candidates,selected:candidates[0]||null,requiresConfirmation:candidates.length>1||Boolean(candidates[0]&&Number(candidates[0].confidence)<0.85)};
  }

  async coverage(tenantId:string,municipalityIbge:string){
    return tenantTx(pool,tenantId,async c=>{
      const r=await c.query(`select sc.dataset_code,sc.scope,sc.availability_status,sc.ingestion_status,coalesce(sc.access_class,sr.access_class) access_class,sc.parser_version,sc.last_checked_at,sc.last_source_update,sc.evidence_hash,sc.metadata,sr.code source_code,sr.title source_title,sr.authority,sr.channel,sr.health,sr.license_terms,p.snapshot_id,p.status publication_status,s.source_date,s.ingested_at,s.validation_status,s.status snapshot_status,s.sha256 from source.coverage sc join source.registry sr on sr.id=sc.source_id left join source.publication p on p.source_id=sc.source_id and p.status='ACTIVE' and (p.municipality_ibge=sc.municipality_ibge or p.municipality_ibge is null) and (p.dataset_code=sc.dataset_code or p.dataset_code is null) left join source.snapshot s on s.id=p.snapshot_id where sc.municipality_ibge=$1 or sc.municipality_ibge is null order by sc.dataset_code,sr.code`,[municipalityIbge]);
      return{municipalityIbge,items:r.rows,summary:{published:r.rows.filter((x:any)=>x.publication_status==='ACTIVE'&&x.validation_status==='PASS').length,discovered:r.rowCount,blocking:r.rows.filter((x:any)=>x.ingestion_status!=='PUBLISHED').map((x:any)=>x.dataset_code)}};
    });
  }

  async legalSearch(tenantId:string,params:{q:string;municipality?:string;baseDate?:string;limit?:number}){
    const q=String(params.q||'').trim();if(q.length<2)throw new HttpException('q deve ter ao menos 2 caracteres',400);const at=cleanDate(params.baseDate);const limit=Math.max(1,Math.min(Number(params.limit||50),200));
    return tenantTx(pool,tenantId,async c=>{
      const r=await c.query(`select d.id document_id,d.kind,d.title,d.authority,d.municipality_ibge,dv.id document_version_id,dv.version_label,dv.publication_date,dv.effective_date,dv.valid_from,dv.valid_to,dv.sha256,a.id article_id,a.hierarchy_path,a.label,a.heading,a.source_locator,left(a.body_text,1200) excerpt,similarity(a.body_text,$1) score from legal.article a join legal.document_version dv on dv.id=a.document_version_id join legal.document d on d.id=dv.document_id where (a.body_text ilike '%'||$1||'%' or a.heading ilike '%'||$1||'%' or a.label ilike '%'||$1||'%') and ($2::text is null or d.municipality_ibge=$2) and (dv.valid_from is null or dv.valid_from <= $3::timestamptz) and (dv.valid_to is null or dv.valid_to > $3::timestamptz) and dv.status in ('REVIEWED','PUBLISHED','ACTIVE','CONFIRMED') order by similarity(a.body_text,$1) desc,dv.effective_date desc nulls last limit $4`,[q,params.municipality||null,`${at}T12:00:00Z`,limit]);
      return{query:q,baseDate:at,items:r.rows};
    });
  }

  async effectiveRules(tenantId:string,params:{municipality:string;zone?:string;baseDate?:string}){
    const municipality=String(params.municipality||'');if(!/^\d{7}$/.test(municipality))throw new HttpException('municipality deve ser geocódigo IBGE de 7 dígitos',400);const at=cleanDate(params.baseDate);
    return tenantTx(pool,tenantId,async c=>{
      const r=await c.query(`select r.id,r.zone_code,r.parameter,r.condition,r.value_numeric,r.value_text,r.unit,r.source_document_version_id,r.source_locator,r.valid_from,r.valid_to,d.title document_title,dv.version_label,dv.effective_date,dv.sha256 from legal.rule r left join legal.document_version dv on dv.id=r.source_document_version_id left join legal.document d on d.id=dv.document_id where r.municipality_ibge=$1 and ($2::text is null or r.zone_code=$2) and r.status='CONFIRMED' and (r.valid_from is null or r.valid_from <= $3::timestamptz) and (r.valid_to is null or r.valid_to > $3::timestamptz) order by r.zone_code,r.parameter,r.created_at desc`,[municipality,params.zone||null,`${at}T12:00:00Z`]);
      const conflicts=await c.query(`select id,zone_code,parameter,rule_ids,status,reason,resolution,created_at from legal.conflict where municipality_ibge=$1 and ($2::text is null or zone_code=$2) and status='OPEN' order by created_at desc`,[municipality,params.zone||null]);
      return{municipality,zone:params.zone||null,baseDate:at,items:r.rows,conflicts:conflicts.rows};
    });
  }

  async effectiveUsePermissions(tenantId:string,params:{municipality:string;zone:string;useCode?:string;baseDate?:string}){
    const municipality=String(params.municipality||'');if(!/^\d{7}$/.test(municipality))throw new HttpException('municipality deve ser geocódigo IBGE de 7 dígitos',400);const zone=String(params.zone||'').trim();if(!zone)throw new HttpException('zone obrigatória',400);const at=cleanDate(params.baseDate);const useCode=String(params.useCode||'').trim()||null;
    return tenantTx(pool,tenantId,async c=>{
      const r=await c.query(`select u.id,u.zone_code,u.use_code,u.use_name,u.permission,u.condition,u.valid_from,u.valid_to,u.source_document_version_id,u.source_article_id,u.source_locator,d.title document_title,dv.version_label,dv.effective_date,dv.sha256 from planning.zone_use_permission u left join legal.document_version dv on dv.id=u.source_document_version_id left join legal.document d on d.id=dv.document_id where u.municipality_ibge=$1 and u.zone_code=$2 and ($3::text is null or u.use_code=$3) and u.status='CONFIRMED' and (u.valid_from is null or u.valid_from <= $4::timestamptz) and (u.valid_to is null or u.valid_to > $4::timestamptz) order by u.use_code,u.created_at desc`,[municipality,zone,useCode,`${at}T12:00:00Z`]);
      return{municipality,zone,useCode,baseDate:at,items:r.rows};
    });
  }

  async intersections(tenantId:string,params:{geometry:any;layerCodes?:string[];domains?:string[];baseDate?:string;limit?:number}){
    const raw=geojson(params.geometry),at=cleanDate(params.baseDate),limit=Math.max(1,Math.min(Number(params.limit||200),1000));const layers=Array.isArray(params.layerCodes)?params.layerCodes.map(String):[];const domains=Array.isArray(params.domains)?params.domains.map(x=>String(x).toUpperCase()):[];
    return tenantTx(pool,tenantId,async c=>{
      const r=await c.query(`with q as (select st_makevalid(st_setsrid(st_geomfromgeojson($1),4326)) geom) select f.id feature_id,l.code layer_code,l.title layer_title,l.domain,f.official_identifier,f.source_snapshot_id,f.attributes,st_area(st_intersection(f.geom,q.geom)::geography) intersection_area_m2,case when st_area(q.geom::geography)>0 then st_area(st_intersection(f.geom,q.geom)::geography)/st_area(q.geom::geography) else null end intersection_ratio,st_asgeojson(st_intersection(f.geom,q.geom))::jsonb intersection_geometry from geo.feature f join geo.layer l on l.id=f.layer_id,q where st_intersects(f.geom,q.geom) and (cardinality($2::text[])=0 or l.code=any($2::text[])) and (cardinality($3::text[])=0 or upper(l.domain)=any($3::text[])) and (f.valid_from is null or f.valid_from <= $4::timestamptz) and (f.valid_to is null or f.valid_to > $4::timestamptz) and (f.superseded_at is null or f.superseded_at > $4::timestamptz) order by intersection_area_m2 desc nulls last limit $5`,[raw,layers,domains,`${at}T12:00:00Z`,limit]);
      return{baseDate:at,count:r.rowCount,items:r.rows};
    });
  }

  async nearby(tenantId:string,params:{lat:number;lon:number;radiusM?:number;layerCodes?:string[];domains?:string[];baseDate?:string;limit?:number}){
    const lat=num(params.lat,'lat'),lon=num(params.lon,'lon');if(lat<-90||lat>90||lon<-180||lon>180)throw new HttpException('coordenadas fora do intervalo',400);const radius=Math.max(1,Math.min(Number(params.radiusM||1000),100000));const at=cleanDate(params.baseDate),limit=Math.max(1,Math.min(Number(params.limit||100),500));const layers=Array.isArray(params.layerCodes)?params.layerCodes.map(String):[];const domains=Array.isArray(params.domains)?params.domains.map(x=>String(x).toUpperCase()):[];
    return tenantTx(pool,tenantId,async c=>{
      const r=await c.query(`with q as (select st_setsrid(st_point($1,$2),4326) geom) select f.id feature_id,l.code layer_code,l.title layer_title,l.domain,f.official_identifier,f.source_snapshot_id,f.attributes,st_distance(f.geom::geography,q.geom::geography) distance_m,st_asgeojson(st_closestpoint(f.geom,q.geom))::jsonb nearest_point from geo.feature f join geo.layer l on l.id=f.layer_id,q where st_dwithin(f.geom::geography,q.geom::geography,$3) and (cardinality($4::text[])=0 or l.code=any($4::text[])) and (cardinality($5::text[])=0 or upper(l.domain)=any($5::text[])) and (f.valid_from is null or f.valid_from <= $6::timestamptz) and (f.valid_to is null or f.valid_to > $6::timestamptz) order by distance_m limit $7`,[lon,lat,radius,layers,domains,`${at}T12:00:00Z`,limit]);
      return{point:{lat,lon},radiusM:radius,baseDate:at,count:r.rowCount,items:r.rows};
    });
  }

  async analysis(tenantId:string,input:ResolverInput,baseDate?:string,context?:Partial<RuleContext>){
    const at=cleanDate(baseDate);
    return tenantTx(pool,tenantId,c=>this.analysisWithClient(c,tenantId,input,at,context));
  }

  async analysisWithClient(c:PoolClient,tenantId:string,input:ResolverInput,at:string,rawContext?:Partial<RuleContext>){
      const resolved=await this.resolveWithClient(c,input,at);if(!resolved.selected)return{status:'INSUFFICIENT_DATA',baseDate:at,resolver:resolved,findings:[],calculations:[],spatial:[],limitations:['Nenhuma parcela versionada foi resolvida para a entrada/data-base.']};
      if(resolved.requiresConfirmation)return{status:'REQUIRES_CONFIRMATION',baseDate:at,resolver:resolved,findings:[],calculations:[],spatial:[],limitations:['Há múltiplos candidatos ou confiança insuficiente. Confirme a parcela antes de produzir conclusão técnica.']};
      const parcel=resolved.selected;const zone=parcel.zones?.[0]||null;const area=Number(parcel.area_m2||0);
      const context:RuleContext={...cleanRuleContext(rawContext),lot_area_m2:area,zone_code:zone?.code||null,municipality_ibge:parcel.municipality_ibge};
      const run=await c.query(`insert into analysis.run(tenant_id,status,base_date,input_snapshot) values($1,'RUNNING',$2,$3::jsonb) returning id,status,base_date,created_at`,[tenantId,at,JSON.stringify({resolverInput:input,resolvedParcelId:parcel.id,municipalityIbge:parcel.municipality_ibge,zoneCode:zone?.code||null,technicalContext:context})]);const runId=run.rows[0].id;
      const rules=await c.query(`select r.id,r.zone_code,r.parameter,r.value_numeric,r.value_text,r.unit,r.condition,r.extraction_metadata,r.source_document_version_id,r.source_article_id,r.source_locator,dv.source_snapshot_id,dv.version_label,dv.effective_date,dv.sha256,d.title document_title from legal.rule r left join legal.document_version dv on dv.id=r.source_document_version_id left join legal.document d on d.id=dv.document_id where r.municipality_ibge=$1 and (r.zone_code=$2::text or r.zone_code is null) and r.status='CONFIRMED' and (r.valid_from is null or r.valid_from <= $3::timestamptz) and (r.valid_to is null or r.valid_to > $3::timestamptz) order by (r.zone_code=$2::text) desc,r.parameter,r.created_at desc`,[parcel.municipality_ibge,zone?.code||null,`${at}T12:00:00Z`]);
      const spatial=await c.query(`with q as (select geom,st_area(geom::geography) area_m2 from geo.parcel where id=$1) select f.id feature_id,l.code layer_code,l.title layer_title,l.domain,f.official_identifier,f.source_snapshot_id,f.attributes,st_area(st_intersection(f.geom,q.geom)::geography) intersection_area_m2,case when q.area_m2>0 then st_area(st_intersection(f.geom,q.geom)::geography)/q.area_m2 else null end intersection_ratio from geo.feature f join geo.layer l on l.id=f.layer_id,q where st_intersects(f.geom,q.geom) and upper(l.domain)=any($2::text[]) and (l.municipality_ibge is null or l.municipality_ibge=$3) and (f.valid_from is null or f.valid_from <= $4::timestamptz) and (f.valid_to is null or f.valid_to > $4::timestamptz) and (f.superseded_at is null or f.superseded_at > $4::timestamptz) order by intersection_area_m2 desc limit 300`,[parcel.id,['ENVIRONMENT','RISK','INFRA','MOBILITY','HERITAGE','LICENSING'],parcel.municipality_ibge,`${at}T12:00:00Z`]);

      const evaluations=new Map<string,ReturnType<typeof evaluateRuleCondition>>();
      for(const rule of rules.rows)evaluations.set(String(rule.id),evaluateRuleCondition(rule.condition||{},context));
      const applicableRules=rules.rows.filter((r:any)=>evaluations.get(String(r.id))?.status==='MATCH');
      const unknownRules=rules.rows.filter((r:any)=>evaluations.get(String(r.id))?.status==='UNKNOWN');

      const conflictGroups=new Map<string,any[]>();for(const rule of applicableRules){const scope=rule.zone_code?`ZONE:${rule.zone_code}`:'MUNICIPAL';const key=`${scope}|${String(rule.parameter).toUpperCase()}|${JSON.stringify(rule.condition||{})}`;const list=conflictGroups.get(key)||[];list.push(rule);conflictGroups.set(key,list);}const conflictedRuleIds=new Set<string>();const conflicts:any[]=[];for(const [key,list] of conflictGroups){const values=new Set(list.map((r:any)=>JSON.stringify([r.value_numeric??null,r.value_text??null,r.unit??null])));if(values.size>1){list.forEach((r:any)=>conflictedRuleIds.add(String(r.id)));conflicts.push({key,parameter:list[0].parameter,zoneCode:list[0].zone_code||null,ruleIds:list.map((r:any)=>r.id),values:[...values].map(x=>JSON.parse(x))});}}

      const ruleFindings=[] as any[];
      for(const rule of rules.rows){
        const evaluation=evaluations.get(String(rule.id))!;const conflicted=conflictedRuleIds.has(String(rule.id));
        const ruleStatus=conflicted?'CONFLICTING':evaluation.status==='MATCH'?'CONFIRMED':evaluation.status==='NO_MATCH'?'NOT_APPLICABLE':'PENDING_CONTEXT';
        await c.query(`insert into planning.analysis_parameter(run_id,parameter,value_numeric,value_text,unit,status,rule_id,source_document_version_id,source_locator) values($1,$2,$3,$4,$5,$6,$7,$8,$9)`,[runId,rule.parameter,rule.value_numeric,rule.value_text,rule.unit,ruleStatus,rule.id,rule.source_document_version_id,rule.source_locator]);
        const value={value:rule.value_numeric??rule.value_text,unit:rule.unit,zone:rule.zone_code||null,ruleId:rule.id,condition:rule.condition||{},conditionEvaluation:evaluation};
        await c.query(`insert into analysis.finding(run_id,category,status,code,title,value) values($1,'URBAN_RULE',$2,$3,$4,$5::jsonb)`,[runId,ruleStatus,rule.parameter,`${rule.parameter} vigente`,JSON.stringify(value)]);
        ruleFindings.push({category:'URBAN_RULE',parameter:rule.parameter,value:rule.value_numeric??rule.value_text,unit:rule.unit,status:ruleStatus,condition:rule.condition,conditionEvaluation:evaluation,evidence:{ruleId:rule.id,documentVersionId:rule.source_document_version_id,articleId:rule.source_article_id,documentTitle:rule.document_title,versionLabel:rule.version_label,effectiveDate:rule.effective_date,sha256:rule.sha256,locator:rule.source_locator}});
      }
      for(const conflict of conflicts)await c.query(`insert into analysis.finding(run_id,category,status,code,title,value) values($1,'LEGAL_CONFLICT','CONFLICTING',$2,$3,$4::jsonb)`,[runId,`CONFLICT_${conflict.parameter}`,`Conflito de regras: ${conflict.parameter}`,JSON.stringify(conflict)]);
      for(const item of spatial.rows){await c.query(`insert into analysis.spatial_relation(run_id,relation_type,layer_code,feature_id,intersection_area_m2,intersection_ratio,source_snapshot_id,evidence) values($1,'INTERSECTS',$2,$3,$4,$5,$6,$7::jsonb)`,[runId,item.layer_code,item.feature_id,item.intersection_area_m2,item.intersection_ratio,item.source_snapshot_id,JSON.stringify({officialIdentifier:item.official_identifier,domain:item.domain,attributes:item.attributes})]);await c.query(`insert into analysis.finding(run_id,category,status,code,title,value) values($1,$2,'CONFIRMED',$3,$4,$5::jsonb)`,[runId,item.domain,`INTERSECTS_${item.layer_code}`,`Interseção com ${item.layer_title}`,JSON.stringify({layerCode:item.layer_code,featureId:item.feature_id,intersectionAreaM2:item.intersection_area_m2,intersectionRatio:item.intersection_ratio})]);}

      const byParam=new Map<string,any>();for(const rule of applicableRules){if(conflictedRuleIds.has(String(rule.id)))continue;const key=String(rule.parameter).toUpperCase();if(!byParam.has(key)||(!byParam.get(key).zone_code&&rule.zone_code))byParam.set(key,rule);}
      const calculations=[] as any[];
      const calc=(code:string,ruleKey:string,formula:string,unit:string,fn:(v:number)=>number)=>{const rule=byParam.get(ruleKey);if(!rule||rule.value_numeric==null)return;const normalized=normalizeRuleNumber(rule);if(normalized==null)return;const value=fn(normalized);calculations.push({code,value,unit,formula,ruleId:rule.id,inputs:{parcelAreaM2:area,[ruleKey]:normalized,rawRuleValue:Number(rule.value_numeric),rawRuleUnit:rule.unit||null,condition:rule.condition||{}}})};
      if(area){calc('POTENTIAL_MIN_M2','CA_MIN','parcel_area_m2 × CA_MIN','m²',v=>area*v);calc('POTENTIAL_BASIC_M2','CA_BASIC','parcel_area_m2 × CA_BASIC','m²',v=>area*v);calc('POTENTIAL_MAX_M2','CA_MAX','parcel_area_m2 × CA_MAX','m²',v=>area*v);calc('MAX_PROJECTION_M2','TO_MAX','parcel_area_m2 × TO_MAX','m²',v=>area*v);calc('MIN_PERMEABLE_M2','TP_MIN','parcel_area_m2 × TP_MIN','m²',v=>area*v);}
      calc('MAX_HEIGHT_M','HEIGHT_MAX_M','HEIGHT_MAX_M','m',v=>v);calc('MAX_FLOORS','FLOORS_MAX','FLOORS_MAX','pavimentos',v=>v);calc('MIN_LOT_AREA_M2','LOT_MIN_AREA_M2','LOT_MIN_AREA_M2','m²',v=>v);calc('MIN_FRONTAGE_M','FRONTAGE_MIN_M','FRONTAGE_MIN_M','m',v=>v);calc('MAX_DENSITY_U_HA','DENSITY_MAX_U_HA','DENSITY_MAX_U_HA','un/ha',v=>v);
      for(const x of calculations)await c.query(`insert into analysis.calculation(run_id,code,value_numeric,unit,formula,inputs,rule_ids,status) values($1,$2,$3,$4,$5,$6::jsonb,$7::uuid[],'CALCULATED') on conflict(run_id,code) do update set value_numeric=excluded.value_numeric,unit=excluded.unit,formula=excluded.formula,inputs=excluded.inputs,rule_ids=excluded.rule_ids`,[runId,x.code,x.value,x.unit,x.formula,JSON.stringify(x.inputs),[x.ruleId]]);

      const snapshotIds=new Set<string>();if(parcel.source_snapshot_id)snapshotIds.add(parcel.source_snapshot_id);if(zone?.source_snapshot_id)snapshotIds.add(zone.source_snapshot_id);for(const rule of rules.rows)if(rule.source_snapshot_id)snapshotIds.add(rule.source_snapshot_id);for(const item of spatial.rows)if(item.source_snapshot_id)snapshotIds.add(item.source_snapshot_id);for(const sid of snapshotIds)await c.query(`insert into analysis.snapshot_ref(run_id,source_snapshot_id,purpose) values($1,$2,'INPUT') on conflict do nothing`,[runId,sid]);
      const status=conflicts.length||unknownRules.length?'NEEDS_REVIEW':(applicableRules.length||spatial.rowCount?'COMPLETED':'INSUFFICIENT_DATA');await c.query(`update analysis.run set status=$2 where id=$1`,[runId,status]);
      return{status,run:{...run.rows[0],status},baseDate:at,resolver:resolved,zone,technicalContext:context,findings:[...ruleFindings,...spatial.rows.map((x:any)=>({category:x.domain,code:`INTERSECTS_${x.layer_code}`,status:'CONFIRMED',value:{layerCode:x.layer_code,featureId:x.feature_id,intersectionAreaM2:x.intersection_area_m2,intersectionRatio:x.intersection_ratio},evidence:{sourceSnapshotId:x.source_snapshot_id,officialIdentifier:x.official_identifier}}))],calculations,spatial:spatial.rows,snapshotIds:[...snapshotIds],limitations:[!zone?'Nenhuma zona vigente foi resolvida para a parcela; apenas regras municipais sem zone_code podem ser consideradas.':null,!rules.rowCount?'Nenhuma regra CONFIRMED vigente foi localizada.':null,unknownRules.length?`${unknownRules.length} regra(s) confirmada(s) dependem de contexto técnico ainda não informado: ${[...new Set(unknownRules.flatMap((r:any)=>evaluations.get(String(r.id))?.unknownFields||[]))].join(', ')}.`:null,conflicts.length?`${conflicts.length} conflito(s) normativo(s) impediram cálculo automático dos parâmetros afetados.`:null,!spatial.rowCount?'Nenhuma camada territorial publicada intersectou a parcela.':null].filter(Boolean)};
  }

  async evidence(tenantId:string,runId:string){
    return tenantTx(pool,tenantId,async c=>{
      const own=await c.query(`select id,status,base_date,input_snapshot,created_at from analysis.run where id=$1 and tenant_id=$2`,[runId,tenantId]);if(!own.rowCount)throw new HttpException('analysis_not_found',404);
      const [params,spatial,calculations,snapshots,findings]=await Promise.all([
        c.query(`select ap.*,d.title document_title,dv.version_label,dv.sha256 from planning.analysis_parameter ap left join legal.document_version dv on dv.id=ap.source_document_version_id left join legal.document d on d.id=dv.document_id where ap.run_id=$1 order by ap.parameter`,[runId]),
        c.query(`select sr.*,l.title layer_title,l.domain from analysis.spatial_relation sr left join geo.feature f on f.id=sr.feature_id left join geo.layer l on l.code=sr.layer_code where sr.run_id=$1 order by sr.layer_code`,[runId]),
        c.query(`select * from analysis.calculation where run_id=$1 order by code`,[runId]),
        c.query(`select ar.purpose,s.id snapshot_id,s.sha256,s.source_date,s.ingested_at,s.parser_version,s.validation_status,s.status,s.object_key,r.code source_code,r.authority from analysis.snapshot_ref ar join source.snapshot s on s.id=ar.source_snapshot_id join source.registry r on r.id=s.source_id where ar.run_id=$1 order by r.code`,[runId]),
        c.query(`select * from analysis.finding where run_id=$1 order by category,created_at`,[runId])
      ]);
      return{run:own.rows[0],parameters:params.rows,spatial:spatial.rows,calculations:calculations.rows,snapshots:snapshots.rows,findings:findings.rows,reproducible:true};
    });
  }

  async labValidationCases(municipalityIbge:string){
    if(!/^\d{7}$/.test(municipalityIbge))throw new HttpException('municipalityIbge inválido',400);
    const profile=await this.pool.query(`select municipality_ibge,status,source_profile,validation_summary,activated_at,updated_at from municipality.lab_profile where municipality_ibge=$1`,[municipalityIbge]);
    if(!profile.rowCount)throw new HttpException('municipality_lab_not_found',404);
    const cases=await this.pool.query(`select id,case_code,input_kind,input_payload,expected_official_reference,expected_parameters,status,reviewer,reviewed_at,notes,created_at from municipality.lab_validation_case where municipality_ibge=$1 order by case_code`,[municipalityIbge]);
    const passed=cases.rows.filter((x:any)=>x.status==='PASS').length;const failed=cases.rows.filter((x:any)=>x.status==='FAIL').length;const pending=cases.rowCount-passed-failed;
    return{profile:profile.rows[0],summary:{total:cases.rowCount,passed,failed,pending,minimum:10,homologationReady:cases.rowCount>=10&&failed===0&&pending===0},items:cases.rows};
  }

  async upsertLabValidationCase(municipalityIbge:string,body:any){
    if(!/^\d{7}$/.test(municipalityIbge))throw new HttpException('municipalityIbge inválido',400);const code=String(body?.caseCode||'').trim();if(!code)throw new HttpException('caseCode obrigatório',400);const kind=String(body?.inputKind||'').trim();if(!kind)throw new HttpException('inputKind obrigatório',400);if(!body?.inputPayload)throw new HttpException('inputPayload obrigatório',400);
    const r=await this.pool.query(`insert into municipality.lab_validation_case(municipality_ibge,case_code,input_kind,input_payload,expected_official_reference,expected_parameters,status,notes) values($1,$2,$3,$4::jsonb,$5,$6::jsonb,'PENDING',$7) on conflict(municipality_ibge,case_code) do update set input_kind=excluded.input_kind,input_payload=excluded.input_payload,expected_official_reference=excluded.expected_official_reference,expected_parameters=excluded.expected_parameters,status='PENDING',reviewer=null,reviewed_at=null,notes=excluded.notes returning *`,[municipalityIbge,code,kind,JSON.stringify(body.inputPayload),body?.expectedOfficialReference||null,JSON.stringify(body?.expectedParameters||{}),body?.notes||null]);return r.rows[0];
  }

  async reviewLabValidationCase(municipalityIbge:string,caseId:string,body:any,reviewer:string){
    const status=String(body?.status||'').toUpperCase();if(!['PASS','FAIL'].includes(status))throw new HttpException('status deve ser PASS ou FAIL',400);if(status==='PASS'&&!body?.expectedOfficialReference)throw new HttpException('PASS exige expectedOfficialReference',400);
    const r=await this.pool.query(`update municipality.lab_validation_case set status=$1,expected_official_reference=coalesce($2,expected_official_reference),expected_parameters=case when $3::jsonb='{}'::jsonb then expected_parameters else $3::jsonb end,reviewer=$4,reviewed_at=now(),notes=coalesce($5,notes) where id=$6 and municipality_ibge=$7 returning *`,[status,body?.expectedOfficialReference||null,JSON.stringify(body?.expectedParameters||{}),reviewer,body?.notes||null,caseId,municipalityIbge]);if(!r.rowCount)throw new HttpException('validation_case_not_found',404);
    const summary=await this.labValidationCases(municipalityIbge);await this.pool.query(`update municipality.lab_profile set validation_summary=$2::jsonb,updated_at=now() where municipality_ibge=$1`,[municipalityIbge,JSON.stringify(summary.summary)]);return r.rows[0];
  }

}
