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

function shareRatio(value:unknown){
  const n=finite(value);
  return n===null?null:(n>1?n/100:n);
}

function addMaxCheck(checks:UrbanRuleCheck[],code:string,rule:UrbanRule|undefined,actual:unknown,calculated:Map<string,FormulaResult>,unit:string,reason:string,requiredOverride?:number|null){
  if(!rule)return;
  const required=requiredOverride===undefined?ruleNumber(rule,calculated):requiredOverride;
  const actualNumber=finite(actual);
  const formulaResult=calculated.get(rule.id);
  if(required===null||actualNumber===null){
    checks.push({code,status:'UNKNOWN',ruleId:rule.id,actual:actualNumber,required,unit,reason:`${reason}:missing_input_or_rule_value`,formulaResult});
    return;
  }
  checks.push({code,status:actualNumber<=required?'PASS':'FAIL',ruleId:rule.id,actual:actualNumber,required,unit,reason,formulaResult});
}

function addMinCheck(checks:UrbanRuleCheck[],code:string,rule:UrbanRule|undefined,actual:unknown,calculated:Map<string,FormulaResult>,unit:string,reason:string,requiredOverride?:number|null){
  if(!rule)return;
  const required=requiredOverride===undefined?ruleNumber(rule,calculated):requiredOverride;
  const actualNumber=finite(actual);
  const formulaResult=calculated.get(rule.id);
  if(required===null||actualNumber===null){
    checks.push({code,status:'UNKNOWN',ruleId:rule.id,actual:actualNumber,required,unit,reason:`${reason}:missing_input_or_rule_value`,formulaResult});
    return;
  }
  checks.push({code,status:actualNumber>=required?'PASS':'FAIL',ruleId:rule.id,actual:actualNumber,required,unit,reason,formulaResult});
}

function usePermission(rule:UrbanRule|undefined):'PERMITTED'|'CONDITIONED'|'PROHIBITED'|'UNKNOWN'|null{
  if(!rule)return null;
  const raw=normalized(rule.value_text||rule.legal_effect);
  if(['PERMITTED','PERMITIDO','ALLOW','ALLOWED','PERMISSIVE'].includes(raw))return 'PERMITTED';
  if(['CONDITIONED','CONDICIONADO','CONDITIONAL'].includes(raw))return 'CONDITIONED';
  if(['PROHIBITED','PROIBIDO','DENY','DENIED','RESTRICTIVE'].includes(raw))return 'PROHIBITED';
  return 'UNKNOWN';
}

const decisionRelevant=(rule:RuntimeRule)=>{
  const code=normalized(rule.rule_code||rule.rule_family);
  return Boolean(rule.hard_constraint)||code.startsWith('USE_')||code.includes('HEIGHT')||code.includes('SETBACK')||code.includes('RECUO')||code.includes('PARKING')||code.includes('VAGAS')||code.includes('DENSITY')||code.includes('CA_')||code.includes('TO_')||code.includes('TP_')||code.includes('LOT_')||code.includes('FRONTAGE')||code.includes('ZEIS')||code.includes('HIS')||code.includes('HMP');
};

export function buildUrbanViability(runtime:RuleRuntimeResult,context:UrbanViabilityContext):UrbanViabilityResult{
  const checks:UrbanRuleCheck[]=[];
  const obligations:UrbanViabilityResult['obligations']=[];
  const calculations:UrbanCalculationMemory[]=runtime.calculated.map(item=>({
    code:item.ruleCode||item.ruleId,
    ruleId:item.ruleId,
    value:item.result.value,
    unit:(runtime.selected.find(rule=>rule.id===item.ruleId)?.unit)||null,
    status:item.result.status,
    unknownFields:item.result.unknownFields,
    reasons:item.result.reasons,
  }));
  const selected=selectedByCode(runtime);
  const calculated=calculatedByRule(runtime);
  const reasons:string[]=[];

  const permissionRule=selected.get('USE_PERMISSION')||selected.get('USE')||selected.get('LAND_USE_PERMISSION');
  if(!context.proposed_use){
    checks.push({code:'USE_PERMISSION',status:'UNKNOWN',ruleId:permissionRule?.id||null,actual:null,required:null,unit:null,reason:'proposed_use_missing'});
  }else{
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

  const caMax=selected.get('CA_MAX');
  if(caMax&&context.computable_area_m2!==undefined)addMaxCheck(checks,'CA_MAX',caMax,context.computable_area_m2,calculated,'m²','maximum_computable_area',ratioAreaLimit(caMax,calculated,context.lot_area_m2));
  const toMax=selected.get('TO_MAX');
  if(toMax&&context.proposed_footprint_m2!==undefined)addMaxCheck(checks,'TO_MAX',toMax,context.proposed_footprint_m2,calculated,'m²','maximum_footprint',ratioAreaLimit(toMax,calculated,context.lot_area_m2));

  const density=selected.get('DENSITY_MAX_U_HA');
  if(density&&context.proposed_units!==undefined){
    const lotArea=finite(context.lot_area_m2);
    const actual=lotArea&&lotArea>0?Number(context.proposed_units)/(lotArea/10000):null;
    addMaxCheck(checks,'DENSITY_MAX_U_HA',density,actual,calculated,'un/ha','maximum_density');
  }

  const affordable=selected.get('ZEIS_HIS_HMP_SHARE_MIN')||selected.get('AFFORDABLE_HOUSING_SHARE_MIN');
  if(affordable)addMinCheck(checks,'AFFORDABLE_HOUSING_SHARE_MIN',affordable,shareRatio(context.affordable_housing_share_pct),calculated,'ratio','minimum_affordable_housing_share');

  for(const code of ['EIV_TRIGGER','PGT_TRIGGER','OUTORGA_REQUIRED','CEPAC_REQUIRED','TDC_REQUIRED']){
    const rule=selected.get(code);if(!rule)continue;
    obligations.push({code,ruleId:rule.id,value:rule.value_text??rule.value_numeric??true,unit:rule.unit||null});
    checks.push({code,status:'CONDITION',ruleId:rule.id,actual:true,required:true,unit:rule.unit||null,reason:'confirmed_procedural_or_financial_obligation'});
  }
  for(const [code,rule] of selected){
    if(!['OUTORGA_COST','OUTORGA_ESTIMATE','CEPAC_QUANTITY','CEPAC_COST','TDC_CAPACITY','TDC_VALUE'].includes(code))continue;
    const formula=calculated.get(rule.id);
    const value=formula?.status==='CALCULATED'?formula.value:rule.value_numeric??rule.value_text??null;
    obligations.push({code,ruleId:rule.id,value,unit:rule.unit||null});
    if(formula&&formula.status!=='CALCULATED')checks.push({code,status:'UNKNOWN',ruleId:rule.id,actual:null,required:null,unit:rule.unit||null,reason:'instrument_formula_not_calculated',formulaResult:formula});
  }

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
