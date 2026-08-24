const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ld-urban-v20-'));
for(const name of ['rule-evaluator','rule-runtime','urban-viability']){
  const src=fs.readFileSync(path.join(root,'services/platform-api/src/territorial',`${name}.ts`),'utf8');
  const out=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;
  fs.writeFileSync(path.join(tmp,`${name}.js`),out);
}
const runtime=require(path.join(tmp,'rule-runtime.js'));
const viability=require(path.join(tmp,'urban-viability.js'));

function run(rules,ctx,deps=[]){
  const graph=runtime.evaluateRuleGraph(rules,deps,ctx,'2026-01-01');
  return viability.buildUrbanViability(graph,ctx);
}

const baseRules=[
  {id:'use',status:'CONFIRMED',rule_code:'USE_PERMISSION',rule_family:'USE',legal_effect:'PERMISSIVE',value_text:'PERMITTED',hard_constraint:true,priority:10,condition:{field:'proposed_use',op:'eq',value:'RESIDENTIAL'}},
  {id:'ca',status:'CONFIRMED',rule_code:'CA_MAX',hard_constraint:true,priority:10,value_numeric:4,unit:'ratio',formula:{op:'multiply',args:[{field:'lot_area_m2'},{const:4}]}},
  {id:'height',status:'CONFIRMED',rule_code:'HEIGHT_MAX_M',hard_constraint:true,priority:10,value_numeric:48,unit:'m'},
  {id:'parking',status:'CONFIRMED',rule_code:'PARKING_MIN',hard_constraint:true,priority:10,value_numeric:20,unit:'spaces'},
];

let result=run(baseRules,{proposed_use:'RESIDENTIAL',lot_area_m2:1000,computable_area_m2:3500,height_m:42,parking_spaces:24});
assert.equal(result.status,'PERMITTED');
assert(result.checks.every(x=>x.status==='PASS'));
assert.equal(result.checks.find(x=>x.code==='CA_MAX').required,4000);
assert(result.calculations.some(x=>x.code==='CA_MAX'&&x.value===4000));

result=run(baseRules,{proposed_use:'RESIDENTIAL',lot_area_m2:1000,computable_area_m2:4100,height_m:42,parking_spaces:24});
assert.equal(result.status,'PROHIBITED');
assert(result.checks.some(x=>x.code==='CA_MAX'&&x.status==='FAIL'));

const directRatios=[
  {id:'use-ratio',status:'CONFIRMED',rule_code:'USE_PERMISSION',value_text:'PERMITTED',hard_constraint:true,priority:10,condition:{field:'proposed_use',op:'eq',value:'RESIDENTIAL'}},
  {id:'ca-ratio',status:'CONFIRMED',rule_code:'CA_MAX',hard_constraint:true,priority:10,value_numeric:4,unit:'ratio'},
  {id:'to-ratio',status:'CONFIRMED',rule_code:'TO_MAX',hard_constraint:true,priority:10,value_numeric:0.7,unit:'ratio'},
];
result=run(directRatios,{proposed_use:'RESIDENTIAL',lot_area_m2:1000,computable_area_m2:3900,proposed_footprint_m2:690});
assert.equal(result.status,'PERMITTED');
assert.equal(result.checks.find(x=>x.code==='CA_MAX').required,4000);
assert.equal(result.checks.find(x=>x.code==='TO_MAX').required,700);

const prohibited=[{id:'use-no',status:'CONFIRMED',rule_code:'USE_PERMISSION',rule_family:'USE',value_text:'PROHIBITED',hard_constraint:true,priority:10,condition:{field:'proposed_use',op:'eq',value:'INDUSTRIAL'}}];
result=run(prohibited,{proposed_use:'INDUSTRIAL',lot_area_m2:1000});
assert.equal(result.status,'PROHIBITED');
assert(result.reasons.includes('confirmed_hard_constraint_failed'));

const conditioned=[
  {id:'use-ok',status:'CONFIRMED',rule_code:'USE_PERMISSION',value_text:'PERMITTED',hard_constraint:true,priority:10,condition:{field:'proposed_use',op:'eq',value:'RESIDENTIAL'}},
  {id:'eiv',status:'CONFIRMED',rule_code:'EIV_TRIGGER',legal_effect:'PROCEDURAL',priority:10,condition:{field:'proposed_gfa_m2',op:'gte',value:20000}},
  {id:'outorga',status:'CONFIRMED',rule_code:'OUTORGA_COST',legal_effect:'COMPUTATIONAL',priority:10,unit:'BRL',formula:{op:'multiply',args:[{field:'lot_area_m2'},{const:125.5}]}}
];
result=run(conditioned,{proposed_use:'RESIDENTIAL',lot_area_m2:1000,proposed_gfa_m2:25000});
assert.equal(result.status,'CONDITIONED');
assert(result.obligations.some(x=>x.code==='EIV_TRIGGER'));
assert(result.obligations.some(x=>x.code==='OUTORGA_COST'&&x.value===125500));
assert(result.calculations.some(x=>x.code==='OUTORGA_COST'&&x.value===125500));

const unknownRules=[
  {id:'use-ok',status:'CONFIRMED',rule_code:'USE_PERMISSION',value_text:'PERMITTED',hard_constraint:true,priority:10,condition:{field:'proposed_use',op:'eq',value:'RESIDENTIAL'}},
  {id:'setback',status:'CONFIRMED',rule_code:'FRONT_SETBACK_MIN_M',hard_constraint:true,priority:10,value_numeric:5,unit:'m',condition:{field:'height_m',op:'gte',value:30}},
];
result=run(unknownRules,{proposed_use:'RESIDENTIAL',lot_area_m2:1000});
assert.equal(result.status,'UNKNOWN');
assert(result.unknownRuleIds.includes('setback'));

result=run([],{lot_area_m2:1000});
assert.equal(result.status,'UNKNOWN');
assert(result.checks.some(x=>x.code==='USE_PERMISSION'&&x.reason==='proposed_use_missing'));

const conflictRules=[
  {id:'use-a',status:'CONFIRMED',rule_code:'USE_PERMISSION',value_text:'PERMITTED',hard_constraint:true,priority:10,condition:{field:'proposed_use',op:'eq',value:'RESIDENTIAL'}},
  {id:'use-b',status:'CONFIRMED',rule_code:'USE_PERMISSION',value_text:'PROHIBITED',hard_constraint:true,priority:10,condition:{field:'proposed_use',op:'eq',value:'RESIDENTIAL'}},
];
result=run(conflictRules,{proposed_use:'RESIDENTIAL',lot_area_m2:1000});
assert.equal(result.status,'CONFLICTING');
assert.deepEqual(result.conflictRuleIds.sort(),['use-a','use-b']);

const zeis=[
  {id:'use-ok',status:'CONFIRMED',rule_code:'USE_PERMISSION',value_text:'PERMITTED',hard_constraint:true,priority:10,condition:{field:'proposed_use',op:'eq',value:'RESIDENTIAL'}},
  {id:'his',status:'CONFIRMED',rule_code:'ZEIS_HIS_HMP_SHARE_MIN',hard_constraint:true,priority:10,value_numeric:30,unit:'%',condition:{field:'zeis_code',op:'exists'}},
];
result=run(zeis,{proposed_use:'RESIDENTIAL',lot_area_m2:1000,zeis_code:'ZEIS-3',affordable_housing_share_pct:35});
assert.equal(result.status,'PERMITTED');
assert(result.checks.some(x=>x.code==='AFFORDABLE_HOUSING_SHARE_MIN'&&x.status==='PASS'));

console.log('v20 urban viability decision runtime OK');
