import {HttpException,Injectable} from '@nestjs/common';
import type {PoolClient} from 'pg';
import {TerritorialService,type ResolverInput} from './territorial.service';
import {normalizeRuleNumber,type RuleContext} from './rule-evaluator';
import {evaluateRuleGraph,type RuleDependency,type RuntimeRule} from './rule-runtime';
import {buildUrbanViability,type UrbanViabilityContext,type UrbanViabilityResult} from './urban-viability';
import {resolveLegalTemporalGraph,type LegalTemporalResult} from './legal-temporal-runtime';
import {deriveAnalysisRunStatus} from './analysis-decision-policy';

type RuleRow=RuntimeRule&{
  parameter?:string|null;
  zone_code?:string|null;
  source_locator?:string|null;
  source_snapshot_id?:string|null;
  document_id?:string|null;
  document_title?:string|null;
  version_label?:string|null;
  effective_date?:string|Date|null;
  sha256?:string|null;
  document_valid_from?:string|Date|null;
  document_valid_to?:string|Date|null;
  document_status?:string|null;
  synthetic_kind?:'ZONE_USE_PERMISSION'|null;
};

type TemporalRuleState={rule:RuleRow;state:'ACTIVE'|'INACTIVE'|'UNKNOWN'|'CONFLICTING';reasons:string[]};

const NUMERIC_FIELDS:Array<keyof UrbanViabilityContext>=[
  'frontage_m','lot_depth_m','road_width_m','slope_pct','existing_floors','height_m','proposed_units',
  'proposed_gfa_m2','proposed_footprint_m2','computable_area_m2','noncomputable_area_m2','parking_spaces',
  'bicycle_spaces','affordable_housing_share_pct','aerodrome_limit_m','easement_overlap_m2','road_widening_area_m2',
  'front_setback_m','side_setback_m','rear_setback_m'
];
const BOOLEAN_FIELDS:Array<keyof RuleContext>=['corner_lot','heritage_overlap','eiv_required','pgt_required'];
const STRING_FIELDS:Array<keyof RuleContext>=['proposed_use','operation_code','zeis_code','housing_category','street_category'];
const CONTEXT_ALIASES:Record<string,keyof UrbanViabilityContext>={
  frontageM:'frontage_m',lotDepthM:'lot_depth_m',roadWidthM:'road_width_m',slopePct:'slope_pct',cornerLot:'corner_lot',
  existingFloors:'existing_floors',proposedUse:'proposed_use',heightM:'height_m',proposedUnits:'proposed_units',
  proposedGfaM2:'proposed_gfa_m2',proposedFootprintM2:'proposed_footprint_m2',computableAreaM2:'computable_area_m2',
  noncomputableAreaM2:'noncomputable_area_m2',parkingSpaces:'parking_spaces',bicycleSpaces:'bicycle_spaces',
  affordableHousingSharePct:'affordable_housing_share_pct',heritageOverlap:'heritage_overlap',aerodromeLimitM:'aerodrome_limit_m',
  easementOverlapM2:'easement_overlap_m2',roadWideningAreaM2:'road_widening_area_m2',operationCode:'operation_code',
  zeisCode:'zeis_code',housingCategory:'housing_category',streetCategory:'street_category',eivRequired:'eiv_required',
  pgtRequired:'pgt_required',frontSetbackM:'front_setback_m',sideSetbackM:'side_setback_m',rearSetbackM:'rear_setback_m'
};

function cleanContext(raw:any):UrbanViabilityContext{
  if(raw==null)return{};
  if(typeof raw!=='object'||Array.isArray(raw))throw new HttpException('context deve ser objeto',400);
  const normalized:any={...raw};
  for(const [from,to] of Object.entries(CONTEXT_ALIASES))if(normalized[to]===undefined&&normalized[from]!==undefined)normalized[to]=normalized[from];
  const out:UrbanViabilityContext={};
  for(const key of NUMERIC_FIELDS){
    const value=(normalized as any)[key];if(value===undefined||value===null||value==='')continue;
    const n=Number(value);if(!Number.isFinite(n)||n<0)throw new HttpException(`${String(key)} inválido`,400);(out as any)[key]=n;
  }
  for(const key of BOOLEAN_FIELDS){const value=(normalized as any)[key];if(value===undefined)continue;if(typeof value!=='boolean')throw new HttpException(`${String(key)} deve ser boolean`,400);(out as any)[key]=value;}
  for(const key of STRING_FIELDS){const value=(normalized as any)[key];if(value===undefined||value===null)continue;const text=String(value).trim();if(!text)throw new HttpException(`${String(key)} inválido`,400);(out as any)[key]=text.slice(0,160);}
  return out;
}

function normalizedCode(rule:RuntimeRule){return String(rule.rule_code||rule.rule_family||rule.id).trim().toUpperCase();}

function sourceTemporalState(rule:RuleRow,temporal:LegalTemporalResult):TemporalRuleState{
  if(!rule.source_document_version_id)return{rule,state:'UNKNOWN',reasons:['missing_source_document_version']};
  const version=temporal.versions[String(rule.source_document_version_id)];
  if(!version)return{rule,state:'UNKNOWN',reasons:['source_document_version_not_in_temporal_graph']};
  if(rule.source_article_id&&temporal.articles[String(rule.source_article_id)]){
    const article=temporal.articles[String(rule.source_article_id)];
    return{rule,state:article.state,reasons:article.reasons};
  }
  return{rule,state:version.state,reasons:version.reasons};
}

function mergeTemporalDecision(decision:UrbanViabilityResult,states:TemporalRuleState[]):UrbanViabilityResult{
  const confirmed=states.filter(x=>x.rule.status==='CONFIRMED');
  const conflicts=confirmed.filter(x=>x.state==='CONFLICTING');
  const unknown=confirmed.filter(x=>x.state==='UNKNOWN');
  if(!conflicts.length&&!unknown.length)return decision;
  const conflictIds=conflicts.map(x=>x.rule.id),unknownIds=unknown.map(x=>x.rule.id);
  return{
    ...decision,
    status:conflictIds.length?'CONFLICTING':'UNKNOWN',
    conflictRuleIds:[...new Set([...decision.conflictRuleIds,...conflictIds])],
    unknownRuleIds:[...new Set([...decision.unknownRuleIds,...unknownIds])],
    reasons:[...decision.reasons,conflictIds.length?'legal_temporal_conflict':'legal_temporal_state_unknown']
  };
}

function rulePersistenceStatus(rule:RuleRow,runtime:ReturnType<typeof evaluateRuleGraph>,temporalState:TemporalRuleState|undefined){
  if(rule.status!=='CONFIRMED')return 'CANDIDATE';
  if(temporalState?.state==='INACTIVE')return 'NOT_APPLICABLE';
  if(temporalState?.state==='UNKNOWN')return 'TEMPORAL_UNKNOWN';
  if(temporalState?.state==='CONFLICTING')return 'CONFLICTING';
  if(runtime.conflicts.some(x=>x.ruleIds.includes(rule.id)))return 'CONFLICTING';
  if(runtime.selected.some(x=>x.id===rule.id))return 'CONFIRMED';
  if(runtime.unknown.some(x=>x.rule.id===rule.id))return 'PENDING_CONTEXT';
  if(runtime.blocked.some(x=>x.rule.id===rule.id))return 'BLOCKED';
  return 'NOT_APPLICABLE';
}

function simpleCalculations(rules:RuntimeRule[],context:UrbanViabilityContext){
  const byCode=new Map(rules.map(rule=>[normalizedCode(rule),rule]));
  const area=Number(context.lot_area_m2||0);const out:any[]=[];
  const ratio=(code:string,output:string,label:string)=>{const rule=byCode.get(code);if(!rule||!area)return;const value=normalizeRuleNumber(rule);if(value===null)return;out.push({code:output,value:area*value,unit:'m²',formula:`lot_area_m2 × ${code}`,ruleId:rule.id,inputs:{lot_area_m2:area,[code]:value}});};
  ratio('CA_MIN','POTENTIAL_MIN_M2','minimum potential');ratio('CA_BASIC','POTENTIAL_BASIC_M2','basic potential');ratio('CA_MAX','POTENTIAL_MAX_M2','maximum potential');ratio('TO_MAX','MAX_PROJECTION_M2','maximum projection');ratio('TP_MIN','MIN_PERMEABLE_M2','minimum permeable area');
  const direct=(code:string,output:string,unit:string)=>{const rule=byCode.get(code);if(!rule)return;const value=normalizeRuleNumber(rule);if(value===null)return;out.push({code:output,value,unit,formula:code,ruleId:rule.id,inputs:{[code]:value}});};
  direct('HEIGHT_MAX_M','MAX_HEIGHT_M','m');direct('FLOORS_MAX','MAX_FLOORS','pavimentos');direct('LOT_MIN_AREA_M2','MIN_LOT_AREA_M2','m²');direct('FRONTAGE_MIN_M','MIN_FRONTAGE_M','m');direct('DENSITY_MAX_U_HA','MAX_DENSITY_U_HA','un/ha');
  return out;
}

@Injectable()
export class AnalysisV20Service{
  constructor(private readonly territorial:TerritorialService){}

  async analysisWithClient(c:PoolClient,tenantId:string,input:ResolverInput,at:string,rawContext?:any){
    const resolved=await this.territorial.resolveWithClient(c,input,at);
    if(!resolved.selected)return{status:'INSUFFICIENT_DATA',baseDate:at,resolver:resolved,decision:null,findings:[],calculations:[],spatial:[],limitations:['Nenhuma parcela versionada foi resolvida para a entrada/data-base.']};
    if(resolved.requiresConfirmation)return{status:'REQUIRES_CONFIRMATION',baseDate:at,resolver:resolved,decision:null,findings:[],calculations:[],spatial:[],limitations:['Há múltiplos candidatos ou confiança insuficiente. Confirme a parcela antes de produzir conclusão técnica.']};

    const parcel=resolved.selected;const zone=parcel.zones?.[0]||null;const area=Number(parcel.area_m2||0);
    const context:UrbanViabilityContext={...cleanContext(rawContext),lot_area_m2:area,zone_code:zone?.code||null,municipality_ibge:parcel.municipality_ibge};
    const timestamp=`${at}T12:00:00Z`;
    const run=await c.query(`insert into analysis.run(tenant_id,status,base_date,input_snapshot) values($1,'RUNNING',$2,$3::jsonb) returning id,status,base_date,created_at`,[tenantId,at,JSON.stringify({contract:'analysis.v20',resolverInput:input,resolvedParcelId:parcel.id,municipalityIbge:parcel.municipality_ibge,zoneCode:zone?.code||null,technicalContext:context})]);
    const runId=run.rows[0].id;

    const rulesQuery=await c.query(`select r.id,r.zone_code,r.parameter,r.rule_code,r.rule_family,r.legal_effect,r.hard_constraint,r.priority,r.formula,r.input_schema,r.output_schema,r.status,r.value_numeric,r.value_text,r.unit,r.condition,r.valid_from,r.valid_to,r.source_document_version_id,r.source_article_id,r.source_locator,dv.source_snapshot_id,dv.document_id,dv.valid_from document_valid_from,dv.valid_to document_valid_to,dv.status document_status,dv.version_label,dv.effective_date,dv.sha256,d.title document_title from legal.rule r left join legal.document_version dv on dv.id=r.source_document_version_id left join legal.document d on d.id=dv.document_id where r.municipality_ibge=$1 and (r.zone_code=$2::text or r.zone_code is null) and r.status in ('CONFIRMED','CANDIDATE') order by (r.zone_code=$2::text) desc,r.priority asc,r.parameter,r.created_at desc`,[parcel.municipality_ibge,zone?.code||null]);
    const ruleRows:RuleRow[]=rulesQuery.rows;

    const bindings=await c.query(`select id,rule_id,binding_type,subject_code,hard_constraint,condition,zone_code,use_code,valid_from,valid_to from planning.rule_binding where municipality_ibge=$1 and status='CONFIRMED' and (zone_code is null or zone_code=$2::text) and (use_code is null or use_code=$3::text) and (valid_from is null or valid_from <= $4::timestamptz) and (valid_to is null or valid_to > $4::timestamptz) order by hard_constraint desc,created_at asc`,[parcel.municipality_ibge,zone?.code||null,context.proposed_use||null,timestamp]);
    const bindingByRule=new Map<string,any>();for(const binding of bindings.rows)if(!bindingByRule.has(String(binding.rule_id)))bindingByRule.set(String(binding.rule_id),binding);
    for(const rule of ruleRows){const binding=bindingByRule.get(String(rule.id));if(binding){rule.rule_code=rule.rule_code||binding.subject_code;rule.hard_constraint=Boolean(rule.hard_constraint||binding.hard_constraint);}}

    if(zone?.code&&context.proposed_use){
      const use=await c.query(`select u.id,u.use_code,u.use_name,u.permission,u.condition,u.valid_from,u.valid_to,u.source_document_version_id,u.source_article_id,u.source_locator,dv.source_snapshot_id,dv.document_id,dv.valid_from document_valid_from,dv.valid_to document_valid_to,dv.status document_status,dv.version_label,dv.effective_date,dv.sha256,d.title document_title from planning.zone_use_permission u left join legal.document_version dv on dv.id=u.source_document_version_id left join legal.document d on d.id=dv.document_id where u.municipality_ibge=$1 and u.zone_code=$2 and u.use_code=$3 and u.status='CONFIRMED' and (u.valid_from is null or u.valid_from <= $4::timestamptz) and (u.valid_to is null or u.valid_to > $4::timestamptz) order by u.created_at desc limit 5`,[parcel.municipality_ibge,zone.code,context.proposed_use,timestamp]);
      for(const item of use.rows)ruleRows.push({id:item.id,status:'CONFIRMED',rule_code:'USE_PERMISSION',rule_family:'USE',legal_effect:String(item.permission||'').toUpperCase()==='PROHIBITED'?'RESTRICTIVE':'PERMISSIVE',hard_constraint:true,priority:1,value_text:item.permission,unit:null,condition:item.condition&&Object.keys(item.condition).length?item.condition:{field:'proposed_use',op:'eq',value:item.use_code},valid_from:item.valid_from,valid_to:item.valid_to,source_document_version_id:item.source_document_version_id,source_article_id:item.source_article_id,source_locator:item.source_locator,source_snapshot_id:item.source_snapshot_id,document_id:item.document_id,document_valid_from:item.document_valid_from,document_valid_to:item.document_valid_to,document_status:item.document_status,version_label:item.version_label,effective_date:item.effective_date,sha256:item.sha256,document_title:item.document_title,parameter:'USE_PERMISSION',synthetic_kind:'ZONE_USE_PERMISSION'});
    }

    const versionIds=[...new Set(ruleRows.map(x=>x.source_document_version_id).filter((x):x is string=>Boolean(x)))];
    let temporal:LegalTemporalResult={asOf:new Date(timestamp).toISOString(),versions:{},articles:{},events:[],pendingRelationIds:[],unknownRelationIds:[],conflicts:[]};
    if(versionIds.length){
      const versions=await c.query(`select id,document_id,valid_from,valid_to,status from legal.document_version where id=any($1::uuid[])`,[versionIds]);
      const relations=await c.query(`select id,from_document_version_id,to_document_version_id,source_article_id,target_article_id,relation_type,valid_from,valid_to,status from legal.relation where to_document_version_id=any($1::uuid[]) or from_document_version_id=any($1::uuid[]) order by valid_from asc nulls last,id`,[versionIds]);
      temporal=resolveLegalTemporalGraph(versions.rows,relations.rows,timestamp);
    }

    const temporalStates=ruleRows.map(rule=>sourceTemporalState(rule,temporal));
    const stateByRule=new Map(temporalStates.map(x=>[x.rule.id,x]));
    const runtimeRules:RuntimeRule[]=ruleRows.map(rule=>({...rule,status:rule.status!=='CONFIRMED'?rule.status:stateByRule.get(rule.id)?.state==='ACTIVE'?'CONFIRMED':`TEMPORAL_${stateByRule.get(rule.id)?.state||'UNKNOWN'}`}));
    const legalRuleIds=new Set(rulesQuery.rows.map((x:any)=>String(x.id)));
    const dependenciesQuery=legalRuleIds.size?await c.query(`select rule_id,depends_on_rule_id,dependency_type,status from legal.rule_dependency where (rule_id=any($1::uuid[]) or depends_on_rule_id=any($1::uuid[])) and status='CONFIRMED'`,[[...legalRuleIds]]):{rows:[]};
    const runtime=evaluateRuleGraph(runtimeRules,dependenciesQuery.rows as RuleDependency[],context,timestamp);
    let decision=buildUrbanViability(runtime,context);
    decision=mergeTemporalDecision(decision,temporalStates);

    const spatial=await c.query(`with q as (select geom,st_area(geom::geography) area_m2 from geo.parcel where id=$1) select f.id feature_id,l.code layer_code,l.title layer_title,l.domain,f.official_identifier,f.source_snapshot_id,f.attributes,st_area(st_intersection(f.geom,q.geom)::geography) intersection_area_m2,case when q.area_m2>0 then st_area(st_intersection(f.geom,q.geom)::geography)/q.area_m2 else null end intersection_ratio from geo.feature f join geo.layer l on l.id=f.layer_id,q where st_intersects(f.geom,q.geom) and upper(l.domain)=any($2::text[]) and (l.municipality_ibge is null or l.municipality_ibge=$3) and (f.valid_from is null or f.valid_from <= $4::timestamptz) and (f.valid_to is null or f.valid_to > $4::timestamptz) and (f.superseded_at is null or f.superseded_at > $4::timestamptz) order by intersection_area_m2 desc limit 300`,[parcel.id,['ENVIRONMENT','RISK','INFRA','MOBILITY','HERITAGE','LICENSING'],parcel.municipality_ibge,timestamp]);

    const findings:any[]=[];
    for(const rule of ruleRows){
      const temporalState=stateByRule.get(rule.id);const status=rulePersistenceStatus(rule,runtime,temporalState);const parameter=String(rule.parameter||rule.rule_code||rule.rule_family||'RULE');
      if(rule.synthetic_kind!=='ZONE_USE_PERMISSION')await c.query(`insert into planning.analysis_parameter(run_id,parameter,value_numeric,value_text,unit,status,rule_id,source_document_version_id,source_locator) values($1,$2,$3,$4,$5,$6,$7,$8,$9)`,[runId,parameter,rule.value_numeric??null,rule.value_text??null,rule.unit??null,status,rule.id,rule.source_document_version_id??null,rule.source_locator??null]);
      const value={value:rule.value_numeric??rule.value_text??null,unit:rule.unit??null,zone:rule.zone_code||zone?.code||null,ruleId:rule.id,ruleCode:rule.rule_code||null,condition:rule.condition||{},temporalState:temporalState?.state||'UNKNOWN',temporalReasons:temporalState?.reasons||[],sourceKind:rule.synthetic_kind||'LEGAL_RULE'};
      await c.query(`insert into analysis.finding(run_id,category,status,code,title,value) values($1,'URBAN_RULE',$2,$3,$4,$5::jsonb)`,[runId,status,parameter,`${parameter} avaliada`,JSON.stringify(value)]);
      findings.push({category:'URBAN_RULE',status,code:parameter,value,evidence:{ruleId:rule.id,documentVersionId:rule.source_document_version_id,articleId:rule.source_article_id,documentTitle:rule.document_title,versionLabel:rule.version_label,effectiveDate:rule.effective_date,sha256:rule.sha256,locator:rule.source_locator}});
    }

    for(const conflict of temporal.conflicts){await c.query(`insert into analysis.finding(run_id,category,status,code,title,value) values($1,'LEGAL_TEMPORAL','CONFLICTING','LEGAL_TEMPORAL_CONFLICT','Conflito temporal de eficácia normativa',$2::jsonb)`,[runId,JSON.stringify(conflict)]);findings.push({category:'LEGAL_TEMPORAL',status:'CONFLICTING',code:'LEGAL_TEMPORAL_CONFLICT',value:conflict});}
    for(const relationId of temporal.unknownRelationIds){const value={relationId};await c.query(`insert into analysis.finding(run_id,category,status,code,title,value) values($1,'LEGAL_TEMPORAL','UNKNOWN','LEGAL_TEMPORAL_UNKNOWN','Relação normativa confirmada sem eficácia determinável',$2::jsonb)`,[runId,JSON.stringify(value)]);findings.push({category:'LEGAL_TEMPORAL',status:'UNKNOWN',code:'LEGAL_TEMPORAL_UNKNOWN',value});}
    for(const check of decision.checks){await c.query(`insert into analysis.finding(run_id,category,status,code,title,value) values($1,'URBAN_VIABILITY',$2,$3,$4,$5::jsonb)`,[runId,check.status,check.code,`Viabilidade: ${check.code}`,JSON.stringify(check)]);findings.push({category:'URBAN_VIABILITY',status:check.status,code:check.code,value:check});}
    await c.query(`insert into analysis.finding(run_id,category,status,code,title,value) values($1,'URBAN_VIABILITY',$2,'OVERALL_VIABILITY','Decisão determinística de viabilidade',$3::jsonb)`,[runId,decision.status,JSON.stringify(decision)]);
    findings.push({category:'URBAN_VIABILITY',status:decision.status,code:'OVERALL_VIABILITY',value:decision});

    for(const item of spatial.rows){await c.query(`insert into analysis.spatial_relation(run_id,relation_type,layer_code,feature_id,intersection_area_m2,intersection_ratio,source_snapshot_id,evidence) values($1,'INTERSECTS',$2,$3,$4,$5,$6,$7::jsonb)`,[runId,item.layer_code,item.feature_id,item.intersection_area_m2,item.intersection_ratio,item.source_snapshot_id,JSON.stringify({officialIdentifier:item.official_identifier,domain:item.domain,attributes:item.attributes})]);await c.query(`insert into analysis.finding(run_id,category,status,code,title,value) values($1,$2,'CONFIRMED',$3,$4,$5::jsonb)`,[runId,item.domain,`INTERSECTS_${item.layer_code}`,`Interseção com ${item.layer_title}`,JSON.stringify({layerCode:item.layer_code,featureId:item.feature_id,intersectionAreaM2:item.intersection_area_m2,intersectionRatio:item.intersection_ratio})]);findings.push({category:item.domain,status:'CONFIRMED',code:`INTERSECTS_${item.layer_code}`,value:item});}

    const simple=simpleCalculations(runtime.selected,context);
    for(const calc of simple)await c.query(`insert into analysis.calculation(run_id,code,value_numeric,unit,formula,inputs,rule_ids,status) values($1,$2,$3,$4,$5,$6::jsonb,$7::uuid[],'CALCULATED') on conflict(run_id,code) do update set value_numeric=excluded.value_numeric,unit=excluded.unit,formula=excluded.formula,inputs=excluded.inputs,rule_ids=excluded.rule_ids,status=excluded.status`,[runId,calc.code,calc.value,calc.unit,calc.formula,JSON.stringify(calc.inputs),legalRuleIds.has(calc.ruleId)?[calc.ruleId]:[]]);
    for(const calc of decision.calculations)await c.query(`insert into analysis.calculation(run_id,code,value_numeric,unit,formula,inputs,rule_ids,status) values($1,$2,$3,$4,$5,$6::jsonb,$7::uuid[],$8) on conflict(run_id,code) do update set value_numeric=excluded.value_numeric,unit=excluded.unit,formula=excluded.formula,inputs=excluded.inputs,rule_ids=excluded.rule_ids,status=excluded.status`,[runId,calc.code,calc.value,calc.unit,'deterministic rule formula',JSON.stringify({technicalContext:context,unknownFields:calc.unknownFields,reasons:calc.reasons}),legalRuleIds.has(calc.ruleId)?[calc.ruleId]:[],calc.status]);

    const snapshotIds=new Set<string>();if(parcel.source_snapshot_id)snapshotIds.add(parcel.source_snapshot_id);if(zone?.source_snapshot_id)snapshotIds.add(zone.source_snapshot_id);for(const rule of ruleRows)if(rule.source_snapshot_id)snapshotIds.add(String(rule.source_snapshot_id));for(const item of spatial.rows)if(item.source_snapshot_id)snapshotIds.add(String(item.source_snapshot_id));for(const sid of snapshotIds)await c.query(`insert into analysis.snapshot_ref(run_id,source_snapshot_id,purpose) values($1,$2,'INPUT') on conflict do nothing`,[runId,sid]);

    const temporalDecisionUnknown=temporalStates.filter(x=>x.rule.status==='CONFIRMED'&&x.state==='UNKNOWN').length+temporal.unknownRelationIds.length;
    const status=deriveAnalysisRunStatus({viabilityStatus:decision.status,hasRules:runtime.selected.length>0,hasSpatialEvidence:spatial.rows.length>0,legalTemporalConflictCount:temporal.conflicts.length,legalTemporalUnknownCount:temporalDecisionUnknown});
    await c.query(`update analysis.run set status=$2 where id=$1`,[runId,status]);

    const limitations=[
      !zone?'Nenhuma zona vigente foi resolvida para a parcela; apenas regras municipais podem ser consideradas.':null,
      !runtime.selected.length?'Nenhuma regra CONFIRMED, temporalmente ativa e aplicável foi selecionada.':null,
      temporal.pendingRelationIds.length?`${temporal.pendingRelationIds.length} relação(ões) legal(is) candidata(s) permanecem fora da decisão até revisão.`:null,
      temporalDecisionUnknown?`${temporalDecisionUnknown} elemento(s) temporal(is) confirmado(s) não puderam ter eficácia determinada.`:null,
      runtime.unknown.length?`${runtime.unknown.length} regra(s) confirmada(s) dependem de contexto técnico ainda não informado.`:null,
      runtime.conflicts.length?`${runtime.conflicts.length} conflito(s) de regra confirmada permanecem sem resolução.`:null,
      !spatial.rows.length?'Nenhuma camada territorial publicada dos domínios críticos intersectou a parcela.':null
    ].filter(Boolean);

    return{status,run:{...run.rows[0],status},baseDate:at,resolver:resolved,zone,technicalContext:context,decision,legalTemporal:temporal,ruleRuntime:{selected:runtime.selected,calculated:runtime.calculated,unknown:runtime.unknown,blocked:runtime.blocked,conflicts:runtime.conflicts,trace:runtime.trace},findings,calculations:[...simple,...decision.calculations],spatial:spatial.rows,snapshotIds:[...snapshotIds],limitations};
  }
}
