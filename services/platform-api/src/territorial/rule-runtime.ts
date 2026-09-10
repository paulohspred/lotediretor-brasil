import {evaluateRuleCondition, type ConditionEvaluation, type RuleContext} from './rule-evaluator';

export type FormulaResult={
  status:'CALCULATED'|'UNKNOWN'|'ERROR';
  value:number|null;
  unknownFields:string[];
  reasons:string[];
};

export type RuntimeRule={
  id:string;
  status:string;
  rule_code?:string|null;
  rule_family?:string|null;
  legal_effect?:string|null;
  hard_constraint?:boolean;
  priority?:number|null;
  valid_from?:string|Date|null;
  valid_to?:string|Date|null;
  condition?:unknown;
  formula?:unknown;
  value_numeric?:number|string|null;
  value_text?:string|null;
  unit?:string|null;
  source_document_version_id?:string|null;
  source_article_id?:string|null;
};

export type RuleDependency={
  rule_id:string;
  depends_on_rule_id:string;
  dependency_type:'REQUIRES'|'OVERRIDES'|'LIMITS'|'EXCLUDES'|'DERIVES_FROM'|string;
  status?:string|null;
};

export type RuleRuntimeResult={
  selected:RuntimeRule[];
  calculated:Array<{ruleId:string;ruleCode:string|null;result:FormulaResult}>;
  unknown:Array<{rule:RuntimeRule;evaluation:ConditionEvaluation;reason?:string}>;
  blocked:Array<{rule:RuntimeRule;reason:string;dependencyRuleId?:string}>;
  conflicts:Array<{kind:'EXCLUDES'|'SAME_PRECEDENCE'|'DEPENDENCY_CYCLE';ruleIds:string[];group?:string;reason:string}>;
  trace:Array<{ruleId:string;state:string;detail?:string}>;
};

function asTime(value:string|Date|null|undefined):number|null{
  if(value===undefined||value===null||value==='')return null;
  const n=value instanceof Date?value.getTime():Date.parse(String(value));
  return Number.isFinite(n)?n:null;
}

export function isRuleEffective(rule:RuntimeRule,asOf:string|Date):boolean{
  const at=asTime(asOf);if(at===null)throw new Error('invalid_as_of');
  const from=asTime(rule.valid_from),to=asTime(rule.valid_to);
  return (from===null||from<=at)&&(to===null||at<to);
}

function readNumber(node:any,ctx:RuleContext):FormulaResult{
  if(typeof node==='number')return Number.isFinite(node)?{status:'CALCULATED',value:node,unknownFields:[],reasons:[]}:{status:'ERROR',value:null,unknownFields:[],reasons:['non_finite_literal']};
  if(!node||typeof node!=='object'||Array.isArray(node))return{status:'ERROR',value:null,unknownFields:[],reasons:['invalid_formula_node']};
  if(Object.prototype.hasOwnProperty.call(node,'const')){
    const n=Number(node.const);return Number.isFinite(n)?{status:'CALCULATED',value:n,unknownFields:[],reasons:[]}:{status:'ERROR',value:null,unknownFields:[],reasons:['invalid_const']};
  }
  if(node.field){
    const key=String(node.field);const raw=(ctx as any)[key];
    if(raw===undefined||raw===null||raw==='')return{status:'UNKNOWN',value:null,unknownFields:[key],reasons:[`missing:${key}`]};
    const n=Number(raw);return Number.isFinite(n)?{status:'CALCULATED',value:n,unknownFields:[],reasons:[]}:{status:'ERROR',value:null,unknownFields:[],reasons:[`non_numeric:${key}`]};
  }
  return evaluateFormula(node,ctx);
}

function combine(parts:FormulaResult[]):FormulaResult|null{
  const error=parts.find(x=>x.status==='ERROR');if(error)return error;
  const unknown=parts.filter(x=>x.status==='UNKNOWN');
  if(unknown.length)return{status:'UNKNOWN',value:null,unknownFields:[...new Set(unknown.flatMap(x=>x.unknownFields))],reasons:unknown.flatMap(x=>x.reasons)};
  return null;
}

export function evaluateFormula(formula:any,ctx:RuleContext):FormulaResult{
  if(formula===undefined||formula===null||formula===''||(typeof formula==='object'&&!Array.isArray(formula)&&Object.keys(formula).length===0))return{status:'UNKNOWN',value:null,unknownFields:[],reasons:['formula_absent']};
  if(typeof formula==='number'||(formula&&typeof formula==='object'&&(Object.prototype.hasOwnProperty.call(formula,'const')||formula.field)))return readNumber(formula,ctx);
  if(!formula||typeof formula!=='object'||Array.isArray(formula))return{status:'ERROR',value:null,unknownFields:[],reasons:['invalid_formula']};
  const op=String(formula.op||'').toLowerCase();
  const args=Array.isArray(formula.args)?formula.args:[];
  if(op==='clamp'){
    const value=readNumber(formula.value??args[0],ctx),min=readNumber(formula.min??args[1],ctx),max=readNumber(formula.max??args[2],ctx);
    const early=combine([value,min,max]);if(early)return early;
    if((min.value as number)>(max.value as number))return{status:'ERROR',value:null,unknownFields:[],reasons:['clamp_min_gt_max']};
    return{status:'CALCULATED',value:Math.min(max.value as number,Math.max(min.value as number,value.value as number)),unknownFields:[],reasons:[]};
  }
  if(!args.length)return{status:'ERROR',value:null,unknownFields:[],reasons:[`missing_args:${op||'unknown'}`]};
  const parts:FormulaResult[]=args.map((x:any):FormulaResult=>readNumber(x,ctx));const early=combine(parts);if(early)return early;
  const values:number[]=parts.map((x:FormulaResult):number=>x.value as number);let value:number;
  switch(op){
    case 'add': value=values.reduce((a:number,b:number)=>a+b,0);break;
    case 'subtract': value=values.slice(1).reduce((a:number,b:number)=>a-b,values[0]);break;
    case 'multiply': value=values.reduce((a:number,b:number)=>a*b,1);break;
    case 'divide':
      if(values.slice(1).some((x:number)=>x===0))return{status:'ERROR',value:null,unknownFields:[],reasons:['division_by_zero']};
      value=values.slice(1).reduce((a:number,b:number)=>a/b,values[0]);break;
    case 'min': value=Math.min(...values);break;
    case 'max': value=Math.max(...values);break;
    case 'floor': value=Math.floor(values[0]);break;
    case 'ceil': value=Math.ceil(values[0]);break;
    case 'round': value=Math.round(values[0]);break;
    case 'abs': value=Math.abs(values[0]);break;
    default:return{status:'ERROR',value:null,unknownFields:[],reasons:[`unsupported_formula_op:${op}`]};
  }
  return Number.isFinite(value)?{status:'CALCULATED',value,unknownFields:[],reasons:[]}:{status:'ERROR',value:null,unknownFields:[],reasons:['non_finite_result']};
}

function groupKey(rule:RuntimeRule){return String(rule.rule_code||rule.rule_family||rule.id);}
function signature(rule:RuntimeRule){return JSON.stringify({legal_effect:rule.legal_effect??null,value_numeric:rule.value_numeric??null,value_text:rule.value_text??null,unit:rule.unit??null,formula:rule.formula??null});}

function dependencyCycles(dependencies:RuleDependency[],matched:Map<string,RuntimeRule>){
  const graph=new Map<string,string[]>();
  for(const dep of dependencies){
    if(dep.dependency_type!=='REQUIRES'||!matched.has(dep.rule_id)||!matched.has(dep.depends_on_rule_id))continue;
    graph.set(dep.rule_id,[...(graph.get(dep.rule_id)||[]),dep.depends_on_rule_id]);
  }
  const state=new Map<string,0|1|2>();
  const stack:string[]=[];
  const found=new Map<string,string[]>();
  const visit=(id:string)=>{
    const s=state.get(id)||0;
    if(s===2)return;
    if(s===1){
      const start=stack.lastIndexOf(id);
      const cycle=[...stack.slice(start),id];
      const unique=[...new Set(cycle)].sort();
      found.set(unique.join(':'),unique);
      return;
    }
    state.set(id,1);stack.push(id);
    for(const next of graph.get(id)||[])visit(next);
    stack.pop();state.set(id,2);
  };
  for(const id of graph.keys())visit(id);
  return[...found.values()];
}

export function evaluateRuleGraph(rules:RuntimeRule[],dependencies:RuleDependency[],ctx:RuleContext,asOf:string|Date):RuleRuntimeResult{
  const result:RuleRuntimeResult={selected:[],calculated:[],unknown:[],blocked:[],conflicts:[],trace:[]};
  const matched=new Map<string,RuntimeRule>();
  const unknownIds=new Set<string>();
  for(const rule of rules){
    if(rule.status!=='CONFIRMED'){result.trace.push({ruleId:rule.id,state:'IGNORED',detail:`status:${rule.status}`});continue;}
    if(!isRuleEffective(rule,asOf)){result.trace.push({ruleId:rule.id,state:'OUT_OF_TIME'});continue;}
    const evaluation=evaluateRuleCondition(rule.condition||{},ctx);
    if(evaluation.status==='MATCH'){matched.set(rule.id,rule);result.trace.push({ruleId:rule.id,state:'MATCH'});}
    else if(evaluation.status==='UNKNOWN'){unknownIds.add(rule.id);result.unknown.push({rule,evaluation});result.trace.push({ruleId:rule.id,state:'UNKNOWN'});}
    else result.trace.push({ruleId:rule.id,state:'NO_MATCH'});
  }

  const activeDeps=dependencies.filter(d=>!d.status||d.status==='CONFIRMED');
  const requires=activeDeps.filter(d=>d.dependency_type==='REQUIRES');

  // REQUIRES is transitive. Evaluate to a fixed point so the result cannot depend on
  // PostgreSQL row order (A->B, B->C must remove A whenever C is unavailable).
  let changed=true;
  while(changed){
    changed=false;
    for(const dep of requires){
      const rule=matched.get(dep.rule_id);if(!rule||matched.has(dep.depends_on_rule_id))continue;
      matched.delete(dep.rule_id);changed=true;
      const reason=unknownIds.has(dep.depends_on_rule_id)?'required_rule_unknown':'required_rule_not_applicable';
      result.blocked.push({rule,reason,dependencyRuleId:dep.depends_on_rule_id});
      result.trace.push({ruleId:rule.id,state:'BLOCKED',detail:`${reason}:${dep.depends_on_rule_id}`});
    }
  }

  // Cyclic confirmed dependency graphs are fail-closed: do not silently treat a cycle
  // as proof that each rule satisfies the other rule's prerequisite.
  for(const ids of dependencyCycles(requires,matched)){
    result.conflicts.push({kind:'DEPENDENCY_CYCLE',ruleIds:ids,reason:'confirmed REQUIRES dependency cycle'});
    for(const id of ids)result.trace.push({ruleId:id,state:'CONFLICT',detail:`dependency_cycle:${ids.join(',')}`});
  }

  for(const dep of activeDeps.filter(d=>d.dependency_type==='OVERRIDES')){
    if(matched.has(dep.rule_id)&&matched.has(dep.depends_on_rule_id)){
      const overridden=matched.get(dep.depends_on_rule_id)!;matched.delete(dep.depends_on_rule_id);
      result.blocked.push({rule:overridden,reason:'overridden',dependencyRuleId:dep.rule_id});
      result.trace.push({ruleId:overridden.id,state:'OVERRIDDEN',detail:`by:${dep.rule_id}`});
    }
  }
  const exclusionSeen=new Set<string>();
  for(const dep of activeDeps.filter(d=>d.dependency_type==='EXCLUDES')){
    if(!matched.has(dep.rule_id)||!matched.has(dep.depends_on_rule_id))continue;
    const ids=[dep.rule_id,dep.depends_on_rule_id].sort();const key=ids.join(':');if(exclusionSeen.has(key))continue;exclusionSeen.add(key);
    result.conflicts.push({kind:'EXCLUDES',ruleIds:ids,reason:'mutually exclusive confirmed rules both apply'});
  }

  const groups=new Map<string,RuntimeRule[]>();
  for(const rule of matched.values()){const key=groupKey(rule);groups.set(key,[...(groups.get(key)||[]),rule]);}
  for(const [group,items] of groups){
    const minPriority=Math.min(...items.map(x=>Number.isFinite(Number(x.priority))?Number(x.priority):100));
    const top=items.filter(x=>(Number.isFinite(Number(x.priority))?Number(x.priority):100)===minPriority).sort((a,b)=>a.id.localeCompare(b.id));
    if(top.length>1&&new Set(top.map(signature)).size>1){
      result.conflicts.push({kind:'SAME_PRECEDENCE',ruleIds:top.map(x=>x.id),group,reason:'different confirmed rules share the same precedence'});
      for(const rule of top)result.trace.push({ruleId:rule.id,state:'CONFLICT',detail:`group:${group}`});
      continue;
    }
    const chosen=top[0];result.selected.push(chosen);result.trace.push({ruleId:chosen.id,state:'SELECTED',detail:`group:${group};priority:${minPriority}`});
    for(const lower of items.filter(x=>x.id!==chosen.id)){
      result.blocked.push({rule:lower,reason:'lower_precedence',dependencyRuleId:chosen.id});
      result.trace.push({ruleId:lower.id,state:'LOWER_PRECEDENCE',detail:`by:${chosen.id}`});
    }
  }
  result.selected.sort((a,b)=>groupKey(a).localeCompare(groupKey(b))||a.id.localeCompare(b.id));
  for(const rule of result.selected){
    if(!rule.formula||typeof rule.formula!=='object'||Array.isArray(rule.formula)||Object.keys(rule.formula as any).length===0)continue;
    result.calculated.push({ruleId:rule.id,ruleCode:rule.rule_code||null,result:evaluateFormula(rule.formula,ctx)});
  }
  return result;
}
