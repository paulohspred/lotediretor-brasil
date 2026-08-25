import {Body,Controller,Get,HttpException,Param,Post,Query,Req} from '@nestjs/common';
import {createHash,randomBytes} from 'crypto';
import {Pool} from 'pg';
import {AuthService} from '../auth.service';
import {tenantTx} from '../common/tenant-db';
import {estimateAvm,marketVelocity,rankLandCandidates} from './v20-market';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});
const B2B_SCOPES=new Set(['market:read','property:read']);

function isoDate(value:any){const v=String(value||'');if(!/^\d{4}-\d{2}-\d{2}$/.test(v))throw new HttpException('baseDate deve estar em YYYY-MM-DD',400);return v;}
async function verifiedSnapshot(c:any,id:string){
  const r=await c.query(`select s.id,s.sha256,s.source_date,s.validation_status,s.status snapshot_status,sr.license_terms,
    case when exists(select 1 from source.publication p where p.snapshot_id=s.id and p.status='ACTIVE') then 'ACTIVE' else null end publication_status
    from source.snapshot s join source.registry sr on sr.id=s.source_id where s.id=$1`,[id]);
  if(!r.rowCount)throw new HttpException('source_snapshot_not_found',404);const x=r.rows[0];
  if(String(x.validation_status).toUpperCase()!=='PASS'||x.publication_status!=='ACTIVE'||!String(x.license_terms||'').trim()||!/^[a-f0-9]{64}$/i.test(String(x.sha256||'')))
    throw new HttpException('source_snapshot_not_eligible_for_operational_market_use',409);
  return x;
}

@Controller('api/v1/property360/v20')
export class Property360V20Controller{
  constructor(private readonly auth:AuthService){}
  private async session(req:any,admin=false){const s=await this.auth.get(req.cookies?.ld_session);if(!s?.organizationId)throw new HttpException('unauthorized',401);const modules=Array.isArray(s.entitlements?.modules)?s.entitlements.modules:[];if(!s.roles?.includes('admin')&&!modules.includes('imovel360'))throw new HttpException('module_not_entitled',403);if(admin&&!s.roles?.includes('admin'))throw new HttpException('forbidden',403);return s;}

  @Post('avm-methodologies')
  async methodology(@Req() req:any,@Body() body:any){
    const s=await this.session(req,true);const version=String(body?.version||'').trim(),algorithm=String(body?.algorithm||'').trim(),status=String(body?.status||'DRAFT').toUpperCase();
    const minComparables=Number(body?.minComparables),maxAgeDays=Number(body?.maxAgeDays);if(!version||!algorithm||!Number.isInteger(minComparables)||minComparables<1||!Number.isInteger(maxAgeDays)||maxAgeDays<0)throw new HttpException('version/algorithm/minComparables/maxAgeDays inválidos',400);
    if(!['DRAFT','CALIBRATED','APPROVED','RETIRED'].includes(status))throw new HttpException('status inválido',400);
    const snapshots:string[]=Array.isArray(body?.calibrationSourceSnapshotIds)?body.calibrationSourceSnapshotIds.map((x:any)=>String(x)):[];
    return tenantTx(pool,s.organizationId,async c=>{
      if(status==='APPROVED'){
        if(!snapshots.length)throw new HttpException('APPROVED exige calibrationSourceSnapshotIds',409);
        for(const id of snapshots)await verifiedSnapshot(c,id);
      }
      const r=await c.query(`insert into property360.avm_methodology(tenant_id,version,status,algorithm,min_comparables,max_age_days,parameters,calibration_metrics,calibration_source_snapshot_ids,valid_from,valid_to,approved_by,approved_at)
        values($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9::uuid[],$10,$11,$12,case when $3='APPROVED' then now() else null end)
        on conflict(tenant_id,version) do update set status=excluded.status,algorithm=excluded.algorithm,min_comparables=excluded.min_comparables,max_age_days=excluded.max_age_days,parameters=excluded.parameters,calibration_metrics=excluded.calibration_metrics,calibration_source_snapshot_ids=excluded.calibration_source_snapshot_ids,valid_from=excluded.valid_from,valid_to=excluded.valid_to,approved_by=excluded.approved_by,approved_at=excluded.approved_at,updated_at=now()
        returning id,version,status,algorithm,min_comparables,max_age_days,parameters,calibration_metrics,calibration_source_snapshot_ids,valid_from,valid_to,approved_by,approved_at`,
        [s.organizationId,version,status,algorithm,minComparables,maxAgeDays,JSON.stringify(body?.parameters||{}),JSON.stringify(body?.calibrationMetrics||{}),snapshots,body?.validFrom||null,body?.validTo||null,status==='APPROVED'?(s.email||s.id):null]);return r.rows[0];
    });
  }

  @Get('market/readiness')
  async readiness(@Req() req:any,@Query('municipality') municipality?:string){
    const s=await this.session(req);if(!municipality)throw new HttpException('municipality obrigatório',400);
    return tenantTx(pool,s.organizationId,async c=>{
      const r=await c.query(`select count(*)::int total,
        count(*) filter(where upper(coalesce(c.source_kind,''))<>'DEMO' and c.source_snapshot_id is not null and s.validation_status='PASS' and coalesce(sr.license_terms,'')<>'' and exists(select 1 from source.publication p where p.snapshot_id=s.id and p.status='ACTIVE'))::int eligible,
        count(*) filter(where upper(coalesce(c.source_kind,''))='DEMO')::int demo
        from property360.comparable c left join source.snapshot s on s.id=c.source_snapshot_id left join source.registry sr on sr.id=s.source_id
        where c.municipality_ibge=$1 and (c.tenant_id=$2 or c.tenant_id is null)`,[municipality,s.organizationId]);
      const x=r.rows[0];return{municipality,totalComparables:x.total,eligibleRealComparables:x.eligible,demoComparables:x.demo,status:x.eligible>0?'REAL_EVIDENCE_AVAILABLE':'REQUIRES_REAL_LICENSED_DATA',policy:'DEMO, unpublished, unvalidated or unlicensed comparables are never eligible for operational AVM.'};
    });
  }

  @Post('avm')
  async avm(@Req() req:any,@Body() body:any){
    const s=await this.session(req);const methodologyVersion=String(body?.methodologyVersion||'').trim(),baseDate=isoDate(body?.baseDate),areaM2=Number(body?.areaM2);if(!methodologyVersion||!(areaM2>0))throw new HttpException('methodologyVersion e areaM2 são obrigatórios',400);
    return tenantTx(pool,s.organizationId,async c=>{
      let municipality=body?.municipality?String(body.municipality):'';const propertyId=body?.propertyId?String(body.propertyId):null;
      if(propertyId){const p=await c.query(`select id,municipality_ibge from property360.property where id=$1 and tenant_id=$2`,[propertyId,s.organizationId]);if(!p.rowCount)throw new HttpException('property_not_found',404);municipality=municipality||String(p.rows[0].municipality_ibge||'');}
      if(!municipality)throw new HttpException('municipality obrigatório',400);
      const m=await c.query(`select id,version,status,min_comparables,max_age_days,algorithm,parameters,calibration_metrics from property360.avm_methodology where tenant_id=$1 and version=$2 and (valid_from is null or valid_from<=$3::date) and (valid_to is null or valid_to>=$3::date)`,[s.organizationId,methodologyVersion,baseDate]);
      if(!m.rowCount)return{status:'REQUIRES_CALIBRATION',methodologyVersion};const method=m.rows[0];
      const comps=await c.query(`select c.id,c.area_m2,c.price_cents,c.source_kind,c.observed_at,c.source_snapshot_id,s.sha256 source_sha256,s.source_date,s.validation_status,sr.license_terms,
        case when exists(select 1 from source.publication p where p.snapshot_id=s.id and p.status='ACTIVE') then 'ACTIVE' else null end publication_status
        from property360.comparable c left join source.snapshot s on s.id=c.source_snapshot_id left join source.registry sr on sr.id=s.source_id
        where c.municipality_ibge=$1 and (c.tenant_id=$2 or c.tenant_id is null) order by c.observed_at desc nulls last limit 500`,[municipality,s.organizationId]);
      const result:any=estimateAvm(areaM2,comps.rows,{version:method.version,status:method.status,min_comparables:Number(method.min_comparables),max_age_days:Number(method.max_age_days)},baseDate);
      if(result.status!=='CALCULATED_FROM_APPROVED_METHOD_AND_REAL_EVIDENCE')return result;
      const run=await c.query(`insert into property360.avm_run(tenant_id,property_id,municipality_ibge,area_m2,model_version,status,estimate_cents,confidence,comparable_ids,assumptions,methodology_id,base_date,source_snapshot_ids,uncertainty,evidence_summary)
        values($1,$2,$3,$4,$5,'CALCULATED',$6,null,$7::uuid[],$8::jsonb,$9,$10::date,$11::uuid[],$12::jsonb,$13::jsonb) returning id,created_at`,
        [s.organizationId,propertyId,municipality,areaM2,method.version,result.estimate_cents,result.comparable_ids,JSON.stringify({algorithm:method.algorithm,parameters:method.parameters,calibrationMetrics:method.calibration_metrics}),method.id,baseDate,result.source_snapshot_ids,JSON.stringify(result.uncertainty_cents),JSON.stringify(result.evidence)]);
      return{...result,avmRunId:run.rows[0].id,createdAt:run.rows[0].created_at};
    });
  }

  @Post('market-series')
  async addMarketSeries(@Req() req:any,@Body() body:any){
    const s=await this.session(req,true);const municipality=String(body?.municipality||''),period=isoDate(body?.period),snapshotId=String(body?.sourceSnapshotId||'');if(!municipality||!snapshotId)throw new HttpException('municipality/sourceSnapshotId obrigatórios',400);
    return tenantTx(pool,s.organizationId,async c=>{await verifiedSnapshot(c,snapshotId);const r=await c.query(`insert into property360.market_series(tenant_id,municipality_ibge,neighborhood,development_id,period,units_launched,units_sold,inventory_end,units_leased,rental_inventory_end,asking_price_cents_m2,asking_rent_cents_m2,source_snapshot_id,data_class)
      values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) returning *`,[s.organizationId,municipality,body?.neighborhood||null,body?.developmentId||null,period,body?.unitsLaunched??null,body?.unitsSold??null,body?.inventoryEnd??null,body?.unitsLeased??null,body?.rentalInventoryEnd??null,body?.askingPriceCentsM2??null,body?.askingRentCentsM2??null,snapshotId,String(body?.dataClass||'OBSERVED')]);return r.rows[0];});
  }

  @Get('market/metrics')
  async metrics(@Req() req:any,@Query('municipality') municipality?:string,@Query('neighborhood') neighborhood?:string){const s=await this.session(req);if(!municipality)throw new HttpException('municipality obrigatório',400);return tenantTx(pool,s.organizationId,async c=>{const rows=(await c.query(`select ms.period,ms.units_launched,ms.units_sold,ms.inventory_end,ms.units_leased,ms.rental_inventory_end,ms.asking_price_cents_m2,ms.asking_rent_cents_m2,ms.source_snapshot_id from property360.market_series ms join source.snapshot ss on ss.id=ms.source_snapshot_id join source.registry sr on sr.id=ss.source_id where ms.tenant_id=$1 and ms.municipality_ibge=$2 and ($3::text is null or ms.neighborhood=$3) and ss.validation_status='PASS' and coalesce(sr.license_terms,'')<>'' and exists(select 1 from source.publication p where p.snapshot_id=ss.id and p.status='ACTIVE') order by ms.period`,[s.organizationId,municipality,neighborhood||null])).rows;return{municipality,neighborhood:neighborhood||null,...marketVelocity(rows),sourceSnapshotIds:[...new Set(rows.map((x:any)=>x.source_snapshot_id))]};});}

  @Post('land-rank')
  async landRank(@Req() req:any,@Body() body:any){const s=await this.session(req);const ids:string[]=Array.isArray(body?.sourceSnapshotIds)?body.sourceSnapshotIds.map((x:any)=>String(x)):[];if(!ids.length)return{status:'REQUIRES_INPUT',missing:['sourceSnapshotIds']};return tenantTx(pool,s.organizationId,async c=>{for(const id of ids)await verifiedSnapshot(c,id);const result=rankLandCandidates(Array.isArray(body?.candidates)?body.candidates:[],body?.objectives||{});const r=await c.query(`insert into property360.land_prospect_run(tenant_id,base_date,objective_spec,input_snapshot,output_snapshot,source_snapshot_ids,created_by) values($1,$2,$3::jsonb,$4::jsonb,$5::jsonb,$6::uuid[],$7) returning id`,[s.organizationId,isoDate(body?.baseDate),JSON.stringify(body?.objectives||{}),JSON.stringify(body?.candidates||[]),JSON.stringify(result),ids,s.email||s.id]);return{...result,runId:r.rows[0].id,sourceSnapshotIds:ids};});}

  @Post('developments/compose')
  async compose(@Req() req:any,@Body() body:any){const s=await this.session(req);const name=String(body?.name||'').trim();const parcelIds:string[]=Array.isArray(body?.parcelIds)?[...new Set<string>(body.parcelIds.map((x:any)=>String(x)))]:[];if(!name||!parcelIds.length)throw new HttpException('name e parcelIds obrigatórios',400);return tenantTx(pool,s.organizationId,async c=>{const p=await c.query(`select count(*)::int count,st_union(geom) geom,sum(st_area(geom::geography)) area from geo.parcel where id=any($1::uuid[]) and (tenant_id is null or tenant_id=$2)`,[parcelIds,s.organizationId]);if(Number(p.rows[0].count)!==parcelIds.length)throw new HttpException('parcel_not_found_or_not_visible',404);const d=await c.query(`insert into property360.development(tenant_id,name,municipality_ibge,status,geom,gross_land_area_m2,attributes) values($1,$2,$3,'PROSPECT',$4,$5,$6::jsonb) returning id,name,status,gross_land_area_m2,created_at`,[s.organizationId,name,body?.municipality||null,p.rows[0].geom,p.rows[0].area,JSON.stringify({compositionPolicy:'explicit_parcel_ids',sourceSnapshotIds:body?.sourceSnapshotIds||[]})]);for(const id of parcelIds)await c.query(`insert into property360.development_parcel(development_id,parcel_id) values($1,$2) on conflict do nothing`,[d.rows[0].id,id]);return{development:d.rows[0],parcelIds};});}

  @Post('b2b/keys')
  async createKey(@Req() req:any,@Body() body:any){const s=await this.session(req,true);const name=String(body?.name||'').trim();const scopes:string[]=Array.isArray(body?.scopes)?[...new Set<string>(body.scopes.map((x:any)=>String(x)))]:[];if(!name||!scopes.length||scopes.some(x=>!B2B_SCOPES.has(x)))throw new HttpException('name/scopes inválidos',400);const secret=`ldp_${randomBytes(32).toString('base64url')}`,hash=createHash('sha256').update(secret).digest('hex'),prefix=secret.slice(0,12);return tenantTx(pool,s.organizationId,async c=>{const r=await c.query(`insert into property360.b2b_api_key(tenant_id,name,key_prefix,key_hash,scopes,expires_at,created_by) values($1,$2,$3,$4,$5,$6,$7) returning id,name,key_prefix,scopes,expires_at,created_at`,[s.organizationId,name,prefix,hash,scopes,body?.expiresAt||null,s.email||s.id]);return{...r.rows[0],apiKey:secret,warning:'API key is returned once; only its SHA-256 hash is persisted.'};});}

  @Post('b2b/keys/:id/revoke')
  async revoke(@Req() req:any,@Param('id') id:string){const s=await this.session(req,true);return tenantTx(pool,s.organizationId,async c=>{const r=await c.query(`update property360.b2b_api_key set revoked_at=now() where id=$1 and tenant_id=$2 and revoked_at is null returning id,revoked_at`,[id,s.organizationId]);if(!r.rowCount)throw new HttpException('api_key_not_found_or_revoked',404);return r.rows[0];});}
}

@Controller('api/v1/property360/b2b/v20')
export class Property360B2BV20Controller{
  private async key(req:any,scope:string){const raw=String(req.headers?.['x-api-key']||'');if(!raw)throw new HttpException('api_key_required',401);const hash=createHash('sha256').update(raw).digest('hex');const r=await pool.query(`select * from property360.resolve_b2b_api_key($1)`,[hash]);if(!r.rowCount)throw new HttpException('invalid_api_key',401);const k=r.rows[0];if(!Array.isArray(k.scopes)||!k.scopes.includes(scope))throw new HttpException('scope_forbidden',403);await tenantTx(pool,k.tenant_id,async c=>{await c.query(`update property360.b2b_api_key set last_used_at=now() where id=$1`,[k.key_id]);});return k;}

  @Get('market/metrics')
  async market(@Req() req:any,@Query('municipality') municipality?:string,@Query('neighborhood') neighborhood?:string){const k=await this.key(req,'market:read');if(!municipality)throw new HttpException('municipality obrigatório',400);return tenantTx(pool,k.tenant_id,async c=>{const rows=(await c.query(`select ms.period,ms.units_launched,ms.units_sold,ms.inventory_end,ms.units_leased,ms.rental_inventory_end,ms.asking_price_cents_m2,ms.asking_rent_cents_m2,ms.source_snapshot_id from property360.market_series ms join source.snapshot ss on ss.id=ms.source_snapshot_id join source.registry sr on sr.id=ss.source_id where ms.tenant_id=$1 and ms.municipality_ibge=$2 and ($3::text is null or ms.neighborhood=$3) and ss.validation_status='PASS' and coalesce(sr.license_terms,'')<>'' and exists(select 1 from source.publication p where p.snapshot_id=ss.id and p.status='ACTIVE') order by ms.period`,[k.tenant_id,municipality,neighborhood||null])).rows;return{municipality,neighborhood:neighborhood||null,...marketVelocity(rows),sourceSnapshotIds:[...new Set(rows.map((x:any)=>x.source_snapshot_id))]};});}

  @Get('properties/:id/summary')
  async property(@Req() req:any,@Param('id') id:string){const k=await this.key(req,'property:read');return tenantTx(pool,k.tenant_id,async c=>{const p=await c.query(`select id,name,address,municipality_ibge,status,tags,attributes,created_at,updated_at from property360.property where id=$1 and tenant_id=$2`,[id,k.tenant_id]);if(!p.rowCount)throw new HttpException('property_not_found',404);const avm=await c.query(`select id,model_version,status,estimate_cents,base_date,uncertainty,source_snapshot_ids,created_at from property360.avm_run where property_id=$1 and tenant_id=$2 order by created_at desc limit 1`,[id,k.tenant_id]);return{property:p.rows[0],latestAvm:avm.rows[0]||null,policy:'B2B response preserves methodology/base-date/source snapshot traceability.'};});}
}
