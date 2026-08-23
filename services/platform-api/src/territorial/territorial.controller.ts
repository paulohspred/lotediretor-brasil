import {Body,Controller,Get,HttpException,HttpStatus,Param,Post,Query,Req} from '@nestjs/common';
import {AuthService} from '../auth.service';
import {withIdempotency} from '../common/idempotency';
import {enqueueOutbox} from '../common/outbox';
import {TerritorialService,ResolverInput} from './territorial.service';

type Session={id?:string;email?:string;roles?:string[];organizationId:string;entitlements?:{modules?:string[]}};

@Controller('api/v1')
export class TerritorialController{
  constructor(private readonly auth:AuthService,private readonly territorial:TerritorialService){}
  private async session(req:any):Promise<Session>{const s=await this.auth.get(req.cookies?.ld_session) as Session|null;if(!s?.organizationId)throw new HttpException('unauthorized',HttpStatus.UNAUTHORIZED);return s;}
  private async admin(req:any){const s=await this.session(req);if(!s.roles?.includes('admin'))throw new HttpException('forbidden',403);return s;}
  private async entitled(req:any){const s=await this.session(req);const modules=Array.isArray(s.entitlements?.modules)?s.entitlements!.modules!:[];if(!s.roles?.includes('admin')&&!modules.includes('imovel360'))throw new HttpException('module_not_entitled',403);return s;}
  private resolverInput(body:any):ResolverInput{
    if(body?.point)return{point:{lat:Number(body.point.lat),lon:Number(body.point.lon)},municipalityIbge:body?.municipalityIbge};
    if(body?.polygon)return{polygon:body.polygon,municipalityIbge:body?.municipalityIbge};
    if(body?.address)return{address:String(body.address),municipalityIbge:body?.municipalityIbge};
    if(body?.identifier)return{identifier:{type:String(body.identifier.type),value:String(body.identifier.value)},municipalityIbge:body?.municipalityIbge};
    if(body?.lat!=null&&body?.lon!=null)return{point:{lat:Number(body.lat),lon:Number(body.lon)},municipalityIbge:body?.municipalityIbge};
    throw new HttpException('resolver input obrigatório',400);
  }

  @Get('parcel/resolve')
  async resolveLegacy(@Req() req:any,@Query('lat') lat:string,@Query('lon') lon:string,@Query('baseDate') baseDate?:string){const s=await this.entitled(req);return this.territorial.resolve(s.organizationId,{point:{lat:Number(lat),lon:Number(lon)}},baseDate);}

  @Post('parcel/resolve')
  async resolve(@Req() req:any,@Body() body:any){const s=await this.entitled(req);return this.territorial.resolve(s.organizationId,this.resolverInput(body),body?.baseDate);}

  @Get('municipalities/:ibge/coverage')
  async coverage(@Req() req:any,@Param('ibge') ibge:string){const s=await this.session(req);if(!/^\d{7}$/.test(ibge))throw new HttpException('ibge inválido',400);return this.territorial.coverage(s.organizationId,ibge);}

  @Get('legal/search')
  async legalSearch(@Req() req:any,@Query('q') q:string,@Query('municipality') municipality?:string,@Query('baseDate') baseDate?:string,@Query('limit') limit?:string){const s=await this.session(req);return this.territorial.legalSearch(s.organizationId,{q,municipality,baseDate,limit:Number(limit||50)});}

  @Get('legal/rules/effective')
  async rules(@Req() req:any,@Query('municipality') municipality:string,@Query('zone') zone?:string,@Query('baseDate') baseDate?:string){const s=await this.session(req);return this.territorial.effectiveRules(s.organizationId,{municipality,zone,baseDate});}

  @Get('legal/uses/effective')
  async uses(@Req() req:any,@Query('municipality') municipality:string,@Query('zone') zone:string,@Query('useCode') useCode?:string,@Query('baseDate') baseDate?:string){const s=await this.session(req);return this.territorial.effectiveUsePermissions(s.organizationId,{municipality,zone,useCode,baseDate});}

  @Post('spatial/intersections')
  async intersections(@Req() req:any,@Body() body:any){const s=await this.session(req);if(!body?.geometry)throw new HttpException('geometry obrigatória',400);return this.territorial.intersections(s.organizationId,{geometry:body.geometry,layerCodes:body.layerCodes,domains:body.domains,baseDate:body.baseDate,limit:body.limit});}

  @Get('nearby')
  async nearby(@Req() req:any,@Query('lat') lat:string,@Query('lon') lon:string,@Query('radiusM') radiusM?:string,@Query('layers') layers?:string,@Query('domains') domains?:string,@Query('baseDate') baseDate?:string,@Query('limit') limit?:string){const s=await this.session(req);return this.territorial.nearby(s.organizationId,{lat:Number(lat),lon:Number(lon),radiusM:Number(radiusM||1000),layerCodes:layers?layers.split(',').filter(Boolean):[],domains:domains?domains.split(',').filter(Boolean):[],baseDate,limit:Number(limit||100)});}

  @Post('analysis')
  async analysis(@Req() req:any,@Body() body:any){
    const s=await this.entitled(req);const key=String(req.headers?.['idempotency-key']||'').trim()||undefined;const input=this.resolverInput(body);
    const idem=await withIdempotency(this.territorial.pool,s.organizationId,'analysis.v19',key,async c=>{
      await c.query(`select set_config('app.tenant_id',$1,true)`,[s.organizationId]);
      const result=await this.territorial.analysisWithClient(c,s.organizationId,input,this.territorial.baseDate(body?.baseDate),body?.context);
      const runId=(result as any)?.run?.id;
      if(runId)await enqueueOutbox(c,'analysis.completed',{analysisRunId:runId,status:(result as any).status,baseDate:(result as any).baseDate,parcelId:(result as any)?.resolver?.selected?.id||null},{tenantId:s.organizationId,aggregateType:'analysis.run',aggregateId:runId,dedupeKey:`analysis.completed:${runId}`});
      return result;
    });
    return{...idem.value,idempotency:{replayed:idem.replayed,key:key||null}};
  }

  @Get('analysis/:id/evidence')
  async evidence(@Req() req:any,@Param('id') id:string){const s=await this.entitled(req);return this.territorial.evidence(s.organizationId,id);}

  @Get('municipality-labs/:ibge/validation-cases')
  async labCases(@Req() req:any,@Param('ibge') ibge:string){await this.admin(req);return this.territorial.labValidationCases(ibge);}

  @Post('municipality-labs/:ibge/validation-cases')
  async addLabCase(@Req() req:any,@Param('ibge') ibge:string,@Body() body:any){await this.admin(req);return this.territorial.upsertLabValidationCase(ibge,body);}

  @Post('municipality-labs/:ibge/validation-cases/:caseId/review')
  async reviewLabCase(@Req() req:any,@Param('ibge') ibge:string,@Param('caseId') caseId:string,@Body() body:any){const s=await this.admin(req);return this.territorial.reviewLabValidationCase(ibge,caseId,body,s.email||s.id||'admin');}

}
