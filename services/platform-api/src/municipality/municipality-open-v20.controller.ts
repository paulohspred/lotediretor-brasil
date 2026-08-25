import {Controller,Get,HttpException,Param,Query} from '@nestjs/common';
import {Pool} from 'pg';
import {openDataProjection} from './v20-governance';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});
function page(raw?:string){const n=Number(raw||100);return Number.isFinite(n)?Math.max(1,Math.min(Math.floor(n),500)):100;}
function cursor(raw?:string){const n=Number(raw||0);return Number.isFinite(n)?Math.max(0,Math.floor(n)):0;}

@Controller('api/v1/municipality/v20/open')
export class MunicipalityOpenDataV20Controller{
  private validIbge(ibge:string){if(!/^\d{7}$/.test(ibge))throw new HttpException('municipality_ibge_invalid',400);}
  private async published(ibge:string,code:string){this.validIbge(ibge);const row=(await pool.query(`select d.id,d.municipality_tenant_id,d.dataset_code,d.title,d.kind,d.visibility,d.status dataset_status,s.status snapshot_status,s.base_date,s.source_snapshot_id,s.checksum_manifest,s.published_at from municipality.dataset d join municipality.tenant mt on mt.id=d.municipality_tenant_id join municipality.dataset_snapshot s on s.dataset_id=d.id and s.status='PUBLISHED' where mt.municipality_ibge=$1 and d.dataset_code=$2 and d.visibility='OPEN' and d.status='ACTIVE'`,[ibge,code.toUpperCase()])).rows[0];if(!row)throw new HttpException('open_dataset_not_found',404);return row;}

  @Get(':ibge/datasets')
  async datasets(@Param('ibge') ibge:string){this.validIbge(ibge);const rows=(await pool.query(`select d.dataset_code,d.title,d.kind,d.visibility,d.status dataset_status,s.status snapshot_status,s.base_date,s.source_snapshot_id,s.checksum_manifest,s.published_at from municipality.dataset d join municipality.tenant mt on mt.id=d.municipality_tenant_id join municipality.dataset_snapshot s on s.dataset_id=d.id and s.status='PUBLISHED' where mt.municipality_ibge=$1 and d.visibility='OPEN' and d.status='ACTIVE' order by d.dataset_code`,[ibge])).rows;return{municipalityIbge:ibge,items:rows.map((r:any)=>openDataProjection({...r,status:r.dataset_status},{...r,status:r.snapshot_status})).filter((r:any)=>r.status==='PUBLIC')};}

  @Get(':ibge/datasets/:code')
  async dataset(@Param('ibge') ibge:string,@Param('code') code:string){const row=await this.published(ibge,code);return openDataProjection({...row,status:row.dataset_status},{...row,status:row.snapshot_status});}

  @Get(':ibge/datasets/:code/records')
  async records(@Param('ibge') ibge:string,@Param('code') code:string,@Query('limit') limitRaw?:string,@Query('cursor') cursorRaw?:string){const ds=await this.published(ibge,code);const limit=page(limitRaw),offset=cursor(cursorRaw);let sql='';switch(String(ds.kind)){
      case 'CTM':sql=`select cadastral_code,st_asgeojson(geom)::jsonb geometry,attributes,source_snapshot_id,valid_from,valid_to from municipality.ctm_parcel where municipality_tenant_id=$1 and source_snapshot_id=$2 order by cadastral_code,valid_from desc nulls last offset $3 limit $4`;break;
      case 'PGV':sql=`select cadastral_code,zone_code,reference_year,land_value_cents_m2,building_value_cents_m2,source_snapshot_id,valid_from,valid_to,attributes from municipality.pgv_value where municipality_tenant_id=$1 and source_snapshot_id=$2 order by reference_year desc,zone_code,cadastral_code offset $3 limit $4`;break;
      case 'IPTU':sql=`select cadastral_code,reference_year,land_value_cents,building_value_cents,tax_value_cents,attributes,source_snapshot_id from municipality.iptu_record where municipality_tenant_id=$1 and source_snapshot_id=$2 order by reference_year desc,cadastral_code offset $3 limit $4`;break;
      case 'ITBI':sql=`select protocol,cadastral_code,transaction_date,declared_value_cents,assessed_value_cents,tax_value_cents,source_snapshot_id,attributes from municipality.itbi_record where municipality_tenant_id=$1 and source_snapshot_id=$2 order by transaction_date desc nulls last,protocol offset $3 limit $4`;break;
      default:throw new HttpException('open_dataset_records_not_supported_for_kind',422);
    }const rows=(await pool.query(sql,[ds.municipality_tenant_id,ds.source_snapshot_id,offset,limit+1])).rows;const hasMore=rows.length>limit;return{municipalityIbge:ibge,dataset:openDataProjection({...ds,status:ds.dataset_status},{...ds,status:ds.snapshot_status}),items:hasMore?rows.slice(0,limit):rows,nextCursor:hasMore?offset+limit:null};}
}
