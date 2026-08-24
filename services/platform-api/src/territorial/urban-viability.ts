import type {RuleContext} from './rule-evaluator';
import type {FormulaResult,RuleRuntimeResult,RuntimeRule} from './rule-runtime';

export type UrbanViabilityStatus='PERMITTED'|'CONDITIONED'|'PROHIBITED'|'UNKNOWN'|'CONFLICTING';

export type UrbanViabilityContext=RuleContext&{
  front_setback_m?:number;
  side_setback_m?:number;
  rear_setback_m?:number;
};

export type UrbanRuleCheck={
  code:string;
  status:'PASS'|'FAIL'|'CONDITION'|'UNKNOWN';
  ruleId:string|null;
  actual:number|string|boolean|null;
  required:number|string|boolean|null;
  unit:string|null;
  reason:string;
  formulaResult?:FormulaResult;
};

export type UrbanCalculationMemory={
  code:string;
  ruleId:string;
  value:number|null;
  unit:string|null;
  status:FormulaResult['status'];
  unknownFields:string[];
  reasons:string[];
};

export type UrbanViabilityResult={
  status:UrbanViabilityStatus;
  checks:UrbanRuleCheck[];
  obligations:Array<{code:string;ruleId:string;value:number|string|boolean|null;unit:string|null}>;
  calculations:UrbanCalculationMemory[];
  unknownRuleIds:string[];
  conflictRuleIds:string[];
  reasons:string[];
};

type UrbanRule=RuntimeRule&{value_text?:string|null};

const normalized=(value:unknown)=>String(value??'').trim().toUpperCase();
const finite=(value:unknown)=>{const n=Number(value);return Number.isFinite(n)?n:null;};
const selectedByCode=(runtime:RuleRuntimeResult)=>new Map(runtime.selected.map(rule=>[normalized(rule.rule_code||rule.rule_family||rule.id),rule as UrbanRule]));
const calculatedByRule=(runtime:RuleRuntimeResult)=>new Map(runtime.calculated.map(item=>[item.ruleId,item.result]));

function ruleNumber(rule:UrbanRule|undefined,calculated:Map<string,FormulaResult>){
  if(!rule)return null;
  const formula=calculated.get(rule.id);
  if(formula?.status==='CALCULATED')return formula.value;
  const raw=finite(rule.value_numeric);
  if(raw===null)return null;
  const unit=normalized(rule.unit);
  return ['%','PERCENT','PCT','POR CENTO'].includes(unit)?raw/100:raw;
}

function ratioAreaLimit(rule:UrbanRule|undefined,calculated:Map<string,FormulaResult>,lotArea:unknown){
  if(!rule)return null;
  const formula=calculated.get(rule.id);
  if(formula?.status==='CALCULATED')return formula.value;
  const ratio=ruleNumber(rule,calculated);
  const area=finite(lotArea);
  return ratio===null||area===null?null:ratio*area;
}

function shareRatio(value:unknown){const n=finite(value);return n===null?null:(n>1?n/100:n);}

function addMaxCheck(checks:UrbanRuleCheck[],code:string,rule:UrbanRule|undefined,actual:unknown,calculated:Map<string,FormulaResult>,unit:string,reason:string,requiredOverride?:number|null){
  if(!rule)return;
  const required=requiredOverride===undefined?ruleNumber(rule,calculated):requiredOverride;
  const actualNumber=finite(actual);
  const formulaResult=calculated.get(rule.id);
  if(required===null||actualNumber===null){checks.push({code,status:'UNKNOWN',ruleId:rule.id,actual:actualNumber,required,unit,reason:`${reason}:missing_input_or_rule_value`,formulaResult});return;}
  checks.push({code,status:actualNumber<=required?'PASS':'FAIL',ruleId:rule.id,actual:actualNumber,required,unit,reason,formulaResult});
}

function addMinCheck(checks:UrbanRuleCheck[],code:string,rule:UrbanRule|undefined,actual:unknown,calculated:Map<string,FormulaResult>,unit:string,reason:string,requiredOverride?:number|null){
  if(!rule)return;
  const required=requiredOverride===undefined?ruleNumber(rule,calculated):requiredOverride;
  const actualNumber=finite(actual);
  const formulaResult=calculated.get(rule.id);
  if(required===null||actualNumber===null){checks.push({code,status:'UNKNOWN',ruleId:rule.id,actual:actualNumber,required,unit,reason:`${reason}:missing_input_or_rule_value`,formulaResult});return;}
  checks.push({code,status:actualNumber>=required?'PASS':'FAIL',ruleId:rule.id,actual:actualNumber,required,unit,reason,formulaResult});
}

function usePermission(rule:UrbanRule|undefined):'PERMITTED'|'CONDITIONED'|'PROHIBITED'|'UNKNOWN'|null{
  if(!rule)return null;
  const raw=normalized(rule.value_text||rule.legal_effect);
  if(['PERMITTED','PERMITIDO','ALLOW','ALLOWED','PERMISSIVE'].includes(raw))return 'PERMITTED';
  if(['CONDITIONED','CONDICIONADO','CONDITIONAL','SPECIAL','TOLERATED','NONCONFORMING'].includes(raw))return 'CONDITIONED';
  if(['PROHIBITED','PROIBIDO','DENY','DENIED','RESTRICTIVE'].includes(raw))return 'PROHIBITED';
  return 'UNKNOWN';
}

function addPresenceRestriction(checks:UrbanRuleCheck[],code:string,rule:UrbanRule|undefined,present:unknown,reason:string){
  if(!rule)return;
  if(typeof present!=='boolean'){checks.push({code,status:'UNKNOWN',ruleId:rule.id,actual:null,required:null,unit:null,reason:`${reason}:spatial_evidence_unknown`});return;}
  if(!present){checks.push({code,status:'PASS',ruleId:rule.id,actual:false,required:false,unit:null,reason:`${reason}:no_overlap`});return;}
  const effect=usePermission(rule);
  if(effect==='PROHIBITED'){checks.push({code,status:'FAIL',ruleId:rule.id,actual:true,required:false,unit:null,reason:`${reason}:confirmed_prohibition`});return;}
  if(effect==='CONDITIONED'||normalized(rule.legal_effect)==='PROCEDURAL'){checks.push({code,status:'CONDITION',ruleId:rule.id,actual:true,required:'REVIEW_OR_CONDITION',unit:null,reason:`${reason}:confirmed_condition`});return;}
  checks.push({code,status:'UNKNOWN',ruleId:rule.id,actual:true,required:rule.value_text??null,unit:null,reason:`${reason}:overlap_effect_not_explicit`});
}

const decisionRelevant=(rule:RuntimeRule)=>{
  const code=normalized(rule.rule_code||rule.rule_family);
  return Boolean(rule.hard_constraint)||code.startsWith('USE_')||code.includes('HEIGHT')||code.includes('SETBACK')||code.includes('RECUO')||code.includes('PARKING')||code.includes('VAGAS')||code.includes('DENSITY')||code.includes('CA_')||code.includes('TO_')||code.includes('TP_')||code.includes('LOT_')||code.includes('FRONTAGE')||code.includes('ZEIS')||code.includes('HIS')||code.includes('HMP')||code.includes('HERITAGE')||code.includes('PATRIMON')||code.includes('AERODROM')||code.includes('AIRSPACE')||code.includes('EASEMENT')||code.includes('SERVIDAO')||code.includes('WIDENING')||code.includes('MELHORAMENTO');
};

export function buildUrbanViability(runtime:RuleRuntimeResult,context:UrbanViabilityContext):UrbanViabilityResult{
  const checks:UrbanRuleCheck[]=[];
  const obligations:UrbanViabilityResult['obligations']=[];
  const calculations:UrbanCalculationMemory[]=runtime.calculated.map(item=>({code:item.ruleCode||item.ruleId,ruleId:item.ruleId,value:item.result.value,unit:(runtime.selected.find(rule=>rule.id===item.ruleId)?.unit)||null,status:item.result.status,unknownFields:item.result.unknownFields,reasons:item.result.reasons}));
  const selected=selectedByCode(runtime);
  const calculated=calculatedByRule(runtime);
  const reasons:string[]=[];

  const permissionRule=selected.get('USE_PERMISSION')||selected.get('USE')||selected.get('LAND_USE_PERMISSION');
  if(!context.proposed_use)checks.push({code:'USE_PERMISSION',status:'UNKNOWN',ruleId:permissionRule?.id||null,actual:null,required:null,unit:null,reason:'proposed_use_missing'});
  else{
    const permission=usePermission(permissionRule);
    if(!permissionRule)checks.push({code:'USE_PERMISSION',status:'UNKNOWN',ruleId:null,actual:context.proposed_use,required:null,unit:null,reason:'missing_confirmed_use_permission'});
    else if(permission==='PROHIBITED')checks.push({code:'USE_PERMISSION',status:'FAIL',ruleId:permissionRule.id,actual:context.proposed_use,required:'PROHIBITED',unit:null,reason:'confirmed_use_prohibition'});
    else if(permission==='CONDITIONED')checks.push({code:'USE_PERMISSION',status:'CONDITION',ruleId:permissionRule.id,actual:context.proposed_use,required:'CONDITIONED',unit:null,reason:'confirmed_use_condition'});
    else if(permission==='PERMITTED')checks.push({code:'USE_PERMISSION',status:'PASS',ruleId:permissionRule.id,actual:context.proposed_use,required:'PERMITTED',unit:null,reason:'confirmed_use_permission'});
    else checks.push({code:'USE_PERMISSION',status:'UNKNOWN',ruleId:permissionRule.id,actual:context.proposed_use,required:null,unit:null,reason:'unrecognized_use_permission_value'});
  }

  addMaxCheck(checks,'HEIGHT_MAX_M',selected.get('HEIGHT_MAX_M'),context.height_m,calculated,'m','height_limit');
  addMinCheck(checks,'LOT_MIN_AREA_M2',selected.get('LOT_MIN_AREA_M2'),context.lot_area_m2,calculated,'m²','minimum_lot_area');
  addMinCheck(checks,'FRONTAGE_MIN_M',selected.get('FRONTAGE_MIN_M'),context.frontage_m,calculated,'m','minimum_frontage');
  addMinCheck(checks,'FRONT_SETBACK_MIN_M',selected.get('FRONT_SETBACK_MIN_M')||selected.get('RECUO_FRONTAL_MIN_M'),context.front_setback_m,calculated,'m','minimum_front_setback');
  addMinCheck(checks,'SIDE_SETBACK_MIN_M',selected.get('SIDE_SETBACK_MIN_M')||selected.get('RECUO_LATERAL_MIN_M'),context.side_setback_m,calculated,'m','minimum_side_setback');
  addMinCheck(checks,'REAR_SETBACK_MIN_M',selected.get('REAR_SETBACK_MIN_M')||selected.get('RECUO_FUNDOS_MIN_M'),context.rear_setback_m,calculated,'m','minimum_rear_setback');
  addMinCheck(checks,'PARKING_MIN',selected.get('PARKING_MIN')||selected.get('PARKING_MIN_SPACES'),context.parking_spaces,calculated,'spaces','minimum_parking');
  addMinCheck(checks,'BICYCLE_PARKING_MIN',selected.get('BICYCLE_PARKING_MIN')||selected.get('BIKE_PARKING_MIN'),context.bicycle_spaces,calculated,'spaces','minimum_bicycle_parking');

  const caMax=selected.get('CA_MAX');
  if(caMax)addMaxCheck(checks,'CA_MAX',caMax,context.computable_area_m2,calculated,'m²','maximum_computable_area',ratioAreaLimit(caMax,calculated,context.lot_area_m2));
  const toMax=selected.get('TO_MAX');
  if(toMax)addMaxCheck(checks,'TO_MAX',toMax,context.proposed_footprint_m2,calculated,'m²','maximum_footprint',ratioAreaLimit(toMax,calculated,context.lot_area_m2));

  const density=selected.get('DENSITY_MAX_U_HA');
  if(density){const lotArea=finite(context.lot_area_m2);const units=finite(context.proposed_units);const actual=lotArea&&lotArea>0&&units!==null?units/(lotArea/10000):null;addMaxCheck(checks,'DENSITY_MAX_U_HA',density,actual,calculated,'un/ha','maximum_density');}

  const affordable=selected.get('ZEIS_HIS_HMP_SHARE_MIN')||selected.get('AFFORDABLE_HOUSING_SHARE_MIN');
  if(affordable)addMinCheck(checks,'AFFORDABLE_HOUSING_SHARE_MIN',affordable,shareRatio(context.affordable_housing_share_pct),calculated,'ratio','minimum_affordable_housing_share');

  const aerodrome=selected.get('AERODROME_HEIGHT_MAX_M')||selected.get('AIRSPACE_HEIGHT_MAX_M')||selected.get('DECEA_HEIGHT_MAX_M');
  if(aerodrome){const legalLimit=ruleNumber(aerodrome,calculated);const spatialLimit=finite(context.aerodrome_limit_m);const required=legalLimit!==null&&spatialLimit!==null?Math.min(legalLimit,spatialLimit):(spatialLimit??legalLimit);addMaxCheck(checks,'AERODROME_HEIGHT_MAX_M',aerodrome,context.height_m,calculated,'m','aerodrome_or_airspace_height_limit',required);}

  const heritage=selected.get('HERITAGE_RESTRICTION')||selected.get('HERITAGE_OVERLAP_RESTRICTION')||selected.get('PATRIMONIO_RESTRICTION');
  addPresenceRestriction(checks,'HERITAGE_RESTRICTION',heritage,context.heritage_overlap,'heritage_overlap');

  const easement=selected.get('EASEMENT_NO_BUILD')||selected.get('SERVIDAO_NO_BUILD');
  if(easement)addMaxCheck(checks,'EASEMENT_NO_BUILD',easement,context.easement_overlap_m2,calculated,'m²','easement_overlap_must_be_zero',0);
  const easementMax=selected.get('EASEMENT_OVERLAP_MAX_M2')||selected.get('SERVIDAO_OVERLAP_MAX_M2');
  if(easementMax)addMaxCheck(checks,'EASEMENT_OVERLAP_MAX_M2',easementMax,context.easement_overlap_m2,calculated,'m²','maximum_easement_overlap');

  const widening=selected.get('ROAD_WIDENING_RESERVE')||selected.get('ROAD_WIDENING_RESTRICTION')||selected.get('MELHORAMENTO_VIARIO_RESTRICTION');
  if(widening){const area=finite(context.road_widening_area_m2);if(area===null)checks.push({code:'ROAD_WIDENING_RESTRICTION',status:'UNKNOWN',ruleId:widening.id,actual:null,required:null,unit:'m²',reason:'road_widening_spatial_evidence_unknown'});else if(area>0){checks.push({code:'ROAD_WIDENING_RESTRICTION',status:'CONDITION',ruleId:widening.id,actual:area,required:'RESERVE_OR_REVIEW',unit:'m²',reason:'confirmed_road_widening_affects_parcel'});obligations.push({code:'ROAD_WIDENING_RESERVE',ruleId:widening.id,value:area,unit:'m²'});}else checks.push({code:'ROAD_WIDENING_RESTRICTION',status:'PASS',ruleId:widening.id,actual:0,required:0,unit:'m²',reason:'no_road_widening_overlap'});}

  for(const code of ['EIV_TRIGGER','PGT_TRIGGER','OUTORGA_REQUIRED','CEPAC_REQUIRED','TDC_REQUIRED']){const rule=selected.get(code);if(!rule)continue;obligations.push({code,ruleId:rule.id,value:rule.value_text??rule.value_numeric??true,unit:rule.unit||null});checks.push({code,status:'CONDITION',ruleId:rule.id,actual:true,required:true,unit:rule.unit||null,reason:'confirmed_procedural_or_financial_obligation'});}
  for(const [code,rule] of selected){if(!['OUTORGA_COST','OUTORGA_ESTIMATE','CEPAC_QUANTITY','CEPAC_COST','TDC_CAPACITY','TDC_VALUE'].includes(code))continue;const formula=calculated.get(rule.id);const value=formula?.status==='CALCULATED'?formula.value:rule.value_numeric??rule.value_text??null;obligations.push({code,ruleId:rule.id,value,unit:rule.unit||null});if(formula&&formula.status!=='CALCULATED')checks.push({code,status:'UNKNOWN',ruleId:rule.id,actual:null,required:null,unit:rule.unit||null,reason:'instrument_formula_not_calculated',formulaResult:formula});}

  const handledRuleIds=new Set(checks.map(check=>check.ruleId).filter((id):id is string=>Boolean(id)).concat(obligations.map(item=>item.ruleId)));
  for(const rule of runtime.selected){if(rule.hard_constraint&&!handledRuleIds.has(rule.id))checks.push({code:normalized(rule.rule_code||rule.rule_family||rule.id),status:'UNKNOWN',ruleId:rule.id,actual:null,required:rule.value_numeric??rule.value_text??null,unit:rule.unit||null,reason:'unsupported_hard_constraint'});}

  const relevantUnknown=runtime.unknown.filter(item=>decisionRelevant(item.rule));
  const unknownRuleIds=[...new Set(relevantUnknown.map(item=>item.rule.id).concat(checks.filter(item=>item.status==='UNKNOWN'&&item.ruleId).map(item=>item.ruleId as string)))];
  const conflictRuleIds=[...new Set(runtime.conflicts.flatMap(conflict=>conflict.ruleIds))];

  let status:UrbanViabilityStatus='PERMITTED';
  if(runtime.conflicts.length){status='CONFLICTING';reasons.push('unresolved_confirmed_rule_conflict');}
  else if(checks.some(check=>check.status==='FAIL')){status='PROHIBITED';reasons.push('confirmed_hard_constraint_failed');}
  else if(relevantUnknown.length||checks.some(check=>check.status==='UNKNOWN')){status='UNKNOWN';reasons.push('decision_relevant_rule_or_input_unknown');}
  else if(checks.some(check=>check.status==='CONDITION')||obligations.length){status='CONDITIONED';reasons.push('confirmed_condition_or_obligation_applies');}
  else reasons.push('all_evaluated_confirmed_constraints_pass');

  return{status,checks,obligations,calculations,unknownRuleIds,conflictRuleIds,reasons};
}
