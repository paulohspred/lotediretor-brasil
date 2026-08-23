import mercurius from 'mercurius';
import {Pool} from 'pg';
import {AuthService} from './auth.service';
import {PLATFORM_VERSION} from './version';
import {tenantQuery,tenantTx} from './common/tenant-db';

const pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});

type Ctx={session:any};
function requireSession(ctx:Ctx){if(!ctx.session?.organizationId)throw new Error('unauthorized');return ctx.session;}
function limitValue(raw:any,max=100){const n=Number(raw??50);return Number.isInteger(n)&&n>0?Math.min(n,max):50;}

export async function registerGraphql(fastify:any,auth:AuthService){
  await fastify.register(mercurius as any,{
    path:'/graphql',
    graphiql:process.env.NODE_ENV!=='production',
    schema:`
      type Health { ok:Boolean!, service:String!, version:String! }
      type Module { code:String!, name:String!, status:String! }
      type Property { id:ID!, name:String!, municipalityIbge:String, createdAt:String }
      type Development { id:ID!, name:String!, status:String, municipalityIbge:String, createdAt:String }
      type Comparable { id:ID!, municipalityIbge:String, neighborhood:String, propertyType:String, areaM2:Float, priceCents:Float, pricePerM2:Float, observedAt:String, sourceKind:String }
      type SourceCoverage { code:String!, title:String!, authority:String, health:String, datasetCode:String, publicationStatus:String, snapshotId:ID, sourceDate:String, ingestedAt:String, parserVersion:String, snapshotStatus:String }
      type Finding { parameter:String!, valueNumeric:Float, valueText:String, unit:String, status:String, ruleId:ID, sourceDocumentVersionId:ID, sourceLocator:String }
      type MunicipalCoverage { datasetCode:String!, availabilityStatus:String!, ingestionStatus:String!, sourceCode:String!, authority:String, publicationStatus:String, snapshotId:ID, validationStatus:String }
      type EffectiveRule { id:ID!, zoneCode:String, parameter:String!, valueNumeric:Float, valueText:String, unit:String, sourceLocator:String, documentTitle:String, versionLabel:String, effectiveDate:String }
      type Entitlements { organizationId:ID!, roles:[String!]!, modules:[String!]! }
      type ReportSummary { id:ID!, status:String!, kind:String!, templateCode:String, templateVersion:Int, rendererVersion:String, sha256:String, createdAt:String, completedAt:String }
      type RuralAssetSummary { id:ID!, name:String, municipalityIbge:String, areaM2:Float, registryRecords:Int!, activeMonitors:Int!, createdAt:String }
      type CondoSummary { id:ID!, name:String!, units:Int!, openWorks:Int!, confirmedRules:Int!, openOccurrences:Int! }
      type SolarProjectSummary { id:ID!, name:String, status:String!, sites:Int!, layouts:Int!, scenarios:Int!, bills:Int! }
      type PropertyFichaSummary { id:ID!, name:String!, municipalityIbge:String, status:String!, analyses:Int!, avmRuns:Int!, reports:Int!, openDiligences:Int!, crmLeads:Int! }
      type Query {
        health:Health!
        modules:[Module!]!
        entitlements:Entitlements!
        properties(limit:Int=50):[Property!]!
        developments(limit:Int=50):[Development!]!
        comparables(municipality:String!,propertyType:String="APARTMENT",limit:Int=50):[Comparable!]!
        sourceCoverage(municipality:String):[SourceCoverage!]!
        analysisFindings(runId:ID!):[Finding!]!
        municipalityCoverage(municipality:String!):[MunicipalCoverage!]!
        effectiveRules(municipality:String!,zone:String,baseDate:String):[EffectiveRule!]!
        propertyFichaSummary(id:ID!):PropertyFichaSummary
        reports(limit:Int=50):[ReportSummary!]!
        ruralAssets(limit:Int=50):[RuralAssetSummary!]!
        condoSummary(id:ID!):CondoSummary
        solarProjectSummary(id:ID!):SolarProjectSummary
      }
    `,
    context:async(request:any)=>({session:await auth.get(request.cookies?.ld_session)}),
    resolvers:{Query:{
      health:()=>({ok:true,service:'platform-api-graphql',version:PLATFORM_VERSION}),
      modules:async(_:any,__:any,ctx:Ctx)=>{const s=requireSession(ctx);return(await tenantQuery(pool,s.organizationId,'select code,name,status from core.module order by sort_order')).rows;},
      entitlements:(_:any,__:any,ctx:Ctx)=>{const s=requireSession(ctx);return{organizationId:s.organizationId,roles:s.roles||[],modules:Array.isArray(s.entitlements?.modules)?s.entitlements.modules:[]};},
      properties:async(_:any,args:any,ctx:Ctx)=>{const s=requireSession(ctx);return(await tenantQuery(pool,s.organizationId,`select id,name,municipality_ibge "municipalityIbge",created_at::text "createdAt" from property360.property where tenant_id=$1 order by created_at desc limit $2`,[s.organizationId,limitValue(args.limit)])).rows;},
      developments:async(_:any,args:any,ctx:Ctx)=>{const s=requireSession(ctx);return(await tenantQuery(pool,s.organizationId,`select id,name,status,municipality_ibge "municipalityIbge",created_at::text "createdAt" from property360.development where tenant_id=$1 order by created_at desc limit $2`,[s.organizationId,limitValue(args.limit)])).rows;},
      comparables:async(_:any,args:any,ctx:Ctx)=>{const s=requireSession(ctx);return(await tenantQuery(pool,s.organizationId,`select id,municipality_ibge "municipalityIbge",neighborhood,property_type "propertyType",area_m2::float8 "areaM2",price_cents::float8 "priceCents",round(price_cents::numeric/nullif(area_m2,0),2)::float8 "pricePerM2",observed_at::text "observedAt",source_kind "sourceKind" from property360.comparable where municipality_ibge=$1 and property_type=$2 order by observed_at desc nulls last limit $3`,[String(args.municipality),String(args.propertyType||'APARTMENT'),limitValue(args.limit)])).rows;},
      sourceCoverage:async(_:any,args:any,ctx:Ctx)=>{const s=requireSession(ctx);return(await tenantQuery(pool,s.organizationId,`select r.code,r.title,r.authority,r.health,p.dataset_code "datasetCode",p.status "publicationStatus",s.id "snapshotId",s.source_date::text "sourceDate",s.ingested_at::text "ingestedAt",s.parser_version "parserVersion",s.status "snapshotStatus" from source.registry r left join source.publication p on p.source_id=r.id and p.status='ACTIVE' and ($1::text is null or p.municipality_ibge is null or p.municipality_ibge=$1) left join source.snapshot s on s.id=p.snapshot_id order by r.code`,[args.municipality||null])).rows;},
      analysisFindings:async(_:any,args:any,ctx:Ctx)=>{const s=requireSession(ctx);return tenantTx(pool,s.organizationId,async c=>{const own=await c.query(`select id from analysis.run where id=$1 and tenant_id=$2`,[String(args.runId),s.organizationId]);if(!own.rowCount)throw new Error('analysis_not_found');return(await c.query(`select parameter,value_numeric::float8 "valueNumeric",value_text "valueText",unit,status,rule_id "ruleId",source_document_version_id "sourceDocumentVersionId",source_locator "sourceLocator" from planning.analysis_parameter where run_id=$1 order by parameter`,[String(args.runId)])).rows;});},
      municipalityCoverage:async(_:any,args:any,ctx:Ctx)=>{const s=requireSession(ctx);return(await tenantQuery(pool,s.organizationId,`select sc.dataset_code "datasetCode",sc.availability_status "availabilityStatus",sc.ingestion_status "ingestionStatus",sr.code "sourceCode",sr.authority,p.status "publicationStatus",p.snapshot_id "snapshotId",sn.validation_status "validationStatus" from source.coverage sc join source.registry sr on sr.id=sc.source_id left join source.publication p on p.source_id=sc.source_id and p.status='ACTIVE' and (p.municipality_ibge=sc.municipality_ibge or p.municipality_ibge is null) and (p.dataset_code=sc.dataset_code or p.dataset_code is null) left join source.snapshot sn on sn.id=p.snapshot_id where sc.municipality_ibge=$1 or sc.municipality_ibge is null order by sc.dataset_code,sr.code`,[String(args.municipality)])).rows;},
      effectiveRules:async(_:any,args:any,ctx:Ctx)=>{const s=requireSession(ctx);const base=String(args.baseDate||new Date().toISOString().slice(0,10));return(await tenantQuery(pool,s.organizationId,`select r.id,r.zone_code "zoneCode",r.parameter,r.value_numeric::float8 "valueNumeric",r.value_text "valueText",r.unit,r.source_locator "sourceLocator",d.title "documentTitle",dv.version_label "versionLabel",dv.effective_date::text "effectiveDate" from legal.rule r left join legal.document_version dv on dv.id=r.source_document_version_id left join legal.document d on d.id=dv.document_id where r.municipality_ibge=$1 and ($2::text is null or r.zone_code=$2) and r.status='CONFIRMED' and (r.valid_from is null or r.valid_from <= $3::timestamptz) and (r.valid_to is null or r.valid_to > $3::timestamptz) order by r.zone_code,r.parameter`,[String(args.municipality),args.zone||null,`${base}T12:00:00Z`])).rows;},
      propertyFichaSummary:async(_:any,args:any,ctx:Ctx)=>{const s=requireSession(ctx);return tenantTx(pool,s.organizationId,async c=>{const p=await c.query(`select id,name,municipality_ibge "municipalityIbge",status from property360.property where id=$1 and tenant_id=$2`,[String(args.id),s.organizationId]);if(!p.rowCount)return null;const [a,v,r,d,l]=await Promise.all([c.query(`select count(*)::int n from analysis.run where property_id=$1 and tenant_id=$2`,[String(args.id),s.organizationId]),c.query(`select count(*)::int n from property360.avm_run where property_id=$1 and tenant_id=$2`,[String(args.id),s.organizationId]),c.query(`select count(*)::int n from report.report_run where tenant_id=$2 and (subject_type='property' and subject_id=$1 or subject_type='analysis' and subject_id in (select id::text from analysis.run where property_id=$1 and tenant_id=$2))`,[String(args.id),s.organizationId]),c.query(`select count(*)::int n from property360.diligence where property_id=$1 and tenant_id=$2 and status not in ('DONE','CLOSED')`,[String(args.id),s.organizationId]),c.query(`select count(*)::int n from crm.lead where property_id=$1 and tenant_id=$2`,[String(args.id),s.organizationId])]);return{...p.rows[0],analyses:a.rows[0].n,avmRuns:v.rows[0].n,reports:r.rows[0].n,openDiligences:d.rows[0].n,crmLeads:l.rows[0].n};});},
      reports:async(_:any,args:any,ctx:Ctx)=>{const s=requireSession(ctx);return(await tenantQuery(pool,s.organizationId,`select id,status,kind,template_code "templateCode",template_version "templateVersion",renderer_version "rendererVersion",sha256,created_at::text "createdAt",completed_at::text "completedAt" from report.report_run where tenant_id=$1 order by created_at desc limit $2`,[s.organizationId,limitValue(args.limit)])).rows;},
      ruralAssets:async(_:any,args:any,ctx:Ctx)=>{const s=requireSession(ctx);const modules=Array.isArray(s.entitlements?.modules)?s.entitlements.modules:[];if(!s.roles?.includes('admin')&&!modules.includes('re-rural'))throw new Error('module_not_entitled');return(await tenantQuery(pool,s.organizationId,`select a.id,a.name,a.municipality_ibge "municipalityIbge",case when a.geom is null then null else st_area(a.geom::geography)::float8 end "areaM2",(select count(*)::int from rural.registry_record rr where rr.asset_id=a.id) "registryRecords",(select count(*)::int from rural.monitor m where m.asset_id=a.id and m.tenant_id=$1 and m.status='ACTIVE') "activeMonitors",a.created_at::text "createdAt" from rural.asset a where a.tenant_id=$1 order by a.created_at desc limit $2`,[s.organizationId,limitValue(args.limit)])).rows;},
      condoSummary:async(_:any,args:any,ctx:Ctx)=>{const s=requireSession(ctx);const modules=Array.isArray(s.entitlements?.modules)?s.entitlements.modules:[];if(!s.roles?.includes('admin')&&!modules.includes('condominio'))throw new Error('module_not_entitled');return tenantTx(pool,s.organizationId,async c=>{const r=await c.query(`select c.id,c.name,(select count(*)::int from condo.unit u where u.condominium_id=c.id and u.status='ACTIVE') units,(select count(*)::int from condo.work_request w where w.condominium_id=c.id and w.status not in ('APPROVED','REJECTED','CLOSED')) "openWorks",(select count(*)::int from condo.rule cr where cr.condominium_id=c.id and cr.status='CONFIRMED') "confirmedRules",(select count(*)::int from condo.occurrence o where o.condominium_id=c.id and o.status='OPEN') "openOccurrences" from condo.condominium c where c.id=$1 and c.tenant_id=$2`,[String(args.id),s.organizationId]);return r.rows[0]||null;});},
      solarProjectSummary:async(_:any,args:any,ctx:Ctx)=>{const s=requireSession(ctx);const modules=Array.isArray(s.entitlements?.modules)?s.entitlements.modules:[];if(!s.roles?.includes('admin')&&!modules.includes('energia-solar'))throw new Error('module_not_entitled');return tenantTx(pool,s.organizationId,async c=>{const r=await c.query(`select p.id,p.name,p.status,(select count(*)::int from solar.site st where st.project_id=p.id) sites,(select count(*)::int from solar.layout l where l.project_id=p.id) layouts,(select count(*)::int from solar.scenario sc where sc.project_id=p.id) scenarios,(select count(*)::int from solar.bill_snapshot b where b.project_id=p.id) bills from solar.project p where p.id=$1 and p.tenant_id=$2`,[String(args.id),s.organizationId]);return r.rows[0]||null;});},
    }}
  });
}
