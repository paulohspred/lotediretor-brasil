export type RuleContext={
  lot_area_m2?:number;
  frontage_m?:number;
  road_width_m?:number;
  corner_lot?:boolean;
  existing_floors?:number;
  proposed_use?:string;
  height_m?:number;
  zone_code?:string|null;
  municipality_ibge?:string;
};

export type ConditionEvaluation={status:'MATCH'|'NO_MATCH'|'UNKNOWN';unknownFields:string[];reasons:string[]};

type Clause={field:string;op?:string;value?:any;values?:any[];min?:number;max?:number};

const aliases:Record<string,keyof RuleContext>={
  lot_area:'lot_area_m2',lot_area_m2:'lot_area_m2',area_lote_m2:'lot_area_m2',parcel_area_m2:'lot_area_m2',
  frontage:'frontage_m',frontage_m:'frontage_m',testada_m:'frontage_m',
  road_width:'road_width_m',road_width_m:'road_width_m',largura_via_m:'road_width_m',
  corner_lot:'corner_lot',lote_esquina:'corner_lot',
  existing_floors:'existing_floors',pavimentos_existentes:'existing_floors',
  proposed_use:'proposed_use',use_class:'proposed_use',uso:'proposed_use',
  height_m:'height_m',altura_m:'height_m',zone_code:'zone_code',municipality_ibge:'municipality_ibge'
};

function fieldName(v:any):keyof RuleContext|string{return aliases[String(v||'').trim().toLowerCase()]||String(v||'').trim();}
function cmp(a:any,b:any,op:string){
  if(op==='eq'||op==='=')return a===b;
  if(op==='ne'||op==='!=')return a!==b;
  if(['lt','lte','gt','gte','<','<=','>','>='].includes(op)){
    const x=Number(a),y=Number(b);if(!Number.isFinite(x)||!Number.isFinite(y))return null;
    if(op==='lt'||op==='<')return x<y;if(op==='lte'||op==='<=')return x<=y;if(op==='gt'||op==='>')return x>y;return x>=y;
  }
  if(op==='in')return Array.isArray(b)&&b.map(String).includes(String(a));
  if(op==='not_in')return Array.isArray(b)&&!b.map(String).includes(String(a));
  if(op==='contains')return String(a).toLowerCase().includes(String(b).toLowerCase());
  return null;
}
function clauseEval(raw:any,ctx:RuleContext):ConditionEvaluation{
  if(!raw||typeof raw!=='object')return{status:'UNKNOWN',unknownFields:[],reasons:['invalid_clause']};
  const field=fieldName(raw.field);const key=field as keyof RuleContext;const value=(ctx as any)[key];
  if(value===undefined||value===null||value==='')return{status:'UNKNOWN',unknownFields:[String(field)],reasons:[`missing:${String(field)}`]};
  const op=String(raw.op||'eq').toLowerCase();
  if(op==='between'){
    const min=Number(raw.min??raw.values?.[0]),max=Number(raw.max??raw.values?.[1]),x=Number(value);
    if(![min,max,x].every(Number.isFinite))return{status:'UNKNOWN',unknownFields:[],reasons:[`invalid_between:${String(field)}`]};
    return x>=min&&x<=max?{status:'MATCH',unknownFields:[],reasons:[]}:{status:'NO_MATCH',unknownFields:[],reasons:[`${String(field)} not between ${min} and ${max}`]};
  }
  const right=op==='in'||op==='not_in'?(raw.values??raw.value):raw.value;const result=cmp(value,right,op);
  if(result===null)return{status:'UNKNOWN',unknownFields:[],reasons:[`unsupported_or_invalid:${String(field)}:${op}`]};
  return result?{status:'MATCH',unknownFields:[],reasons:[]}:{status:'NO_MATCH',unknownFields:[],reasons:[`${String(field)} ${op} ${JSON.stringify(right)} not satisfied`]};
}
function mergeAll(items:ConditionEvaluation[]):ConditionEvaluation{
  const unknown=[...new Set(items.flatMap(x=>x.unknownFields))],reasons=items.flatMap(x=>x.reasons);
  if(items.some(x=>x.status==='NO_MATCH'))return{status:'NO_MATCH',unknownFields:unknown,reasons};
  if(items.some(x=>x.status==='UNKNOWN'))return{status:'UNKNOWN',unknownFields:unknown,reasons};
  return{status:'MATCH',unknownFields:[],reasons:[]};
}
function mergeAny(items:ConditionEvaluation[]):ConditionEvaluation{
  if(items.some(x=>x.status==='MATCH'))return{status:'MATCH',unknownFields:[],reasons:[]};
  const unknown=[...new Set(items.flatMap(x=>x.unknownFields))],reasons=items.flatMap(x=>x.reasons);
  if(items.some(x=>x.status==='UNKNOWN'))return{status:'UNKNOWN',unknownFields:unknown,reasons};
  return{status:'NO_MATCH',unknownFields:[],reasons};
}

export function evaluateRuleCondition(condition:any,ctx:RuleContext):ConditionEvaluation{
  if(!condition||typeof condition!=='object'||Array.isArray(condition)||Object.keys(condition).length===0)return{status:'MATCH',unknownFields:[],reasons:[]};
  if(Array.isArray(condition.all))return mergeAll(condition.all.map((x:any)=>evaluateRuleCondition(x,ctx)));
  if(Array.isArray(condition.any))return mergeAny(condition.any.map((x:any)=>evaluateRuleCondition(x,ctx)));
  if(condition.not){const r=evaluateRuleCondition(condition.not,ctx);if(r.status==='UNKNOWN')return r;return r.status==='MATCH'?{status:'NO_MATCH',unknownFields:[],reasons:['not condition matched']}:{status:'MATCH',unknownFields:[],reasons:[]};}
  if(condition.field)return clauseEval(condition,ctx);
  // Backward-compatible compact form: {lot_area_m2:{lte:500}, corner_lot:true}
  const results:ConditionEvaluation[]=[];
  for(const [rawField,spec] of Object.entries(condition)){
    if(['extractor','excerpt','offset','article_path'].includes(rawField))continue; // legacy extraction metadata must not change applicability.
    if(spec&&typeof spec==='object'&&!Array.isArray(spec)){
      const pairs=Object.entries(spec as any);if(!pairs.length)continue;
      for(const [op,value] of pairs)results.push(clauseEval({field:rawField,op,value},ctx));
    }else results.push(clauseEval({field:rawField,op:'eq',value:spec},ctx));
  }
  return results.length?mergeAll(results):{status:'MATCH',unknownFields:[],reasons:[]};
}

export function normalizeRuleNumber(rule:any){
  const raw=Number(rule?.value_numeric);if(!Number.isFinite(raw))return null;const u=String(rule?.unit||'').trim().toLowerCase();return (u==='%'||u==='percent'||u==='pct'||u==='por cento')?raw/100:raw;
}
