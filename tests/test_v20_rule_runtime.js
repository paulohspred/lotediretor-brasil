const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ld-rule-v20-'));
for(const name of ['rule-evaluator','rule-runtime']){
  const src=fs.readFileSync(path.join(root,'services/platform-api/src/territorial',`${name}.ts`),'utf8');
  const out=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;
  fs.writeFileSync(path.join(tmp,`${name}.js`),out);
}
const evaluator=require(path.join(tmp,'rule-evaluator.js'));
const runtime=require(path.join(tmp,'rule-runtime.js'));

// Richer urban context remains tri-state: missing factual inputs cannot become false certainty.
assert.equal(evaluator.evaluateRuleCondition({field:'exige_eiv',op:'eq',value:true},{eiv_required:true}).status,'MATCH');
assert.equal(evaluator.evaluateRuleCondition({field:'sobreposicao_servidao_m2',op:'gt',value:0},{}).status,'UNKNOWN');
assert.equal(evaluator.evaluateRuleCondition({field:'zeis',op:'exists'},{}).status,'NO_MATCH');

// Formula execution is deterministic and never evals arbitrary source text.
let f=runtime.evaluateFormula({op:'subtract',args:[{op:'multiply',args:[{field:'lot_area_m2'},{const:2.5}]},{field:'noncomputable_area_m2'}]},{lot_area_m2:1000,noncomputable_area_m2:100});
assert.deepEqual(f,{status:'CALCULATED',value:2400,unknownFields:[],reasons:[]});
f=runtime.evaluateFormula({op:'multiply',args:[{field:'lot_area_m2'},{field:'missing_factor'}]},{lot_area_m2:1000});
assert.equal(f.status,'UNKNOWN');assert.deepEqual(f.unknownFields,['missing_factor']);
assert.equal(runtime.evaluateFormula({op:'divide',args:[{const:10},{const:0}]},{}).status,'ERROR');

const rules=[
  {id:'ca-base',status:'CONFIRMED',rule_code:'CA_MAX',priority:100,valid_from:'2024-01-01',condition:{field:'zone_code',op:'eq',value:'ZEU'},formula:{op:'multiply',args:[{field:'lot_area_m2'},{const:2}]}},
  {id:'ca-special',status:'CONFIRMED',rule_code:'CA_MAX',priority:10,valid_from:'2024-01-01',condition:{all:[{field:'zone_code',op:'eq',value:'ZEU'},{field:'operation_code',op:'eq',value:'OUC'}]},formula:{op:'multiply',args:[{field:'lot_area_m2'},{const:4}]}},
  {id:'eiv',status:'CONFIRMED',rule_code:'EIV_TRIGGER',priority:100,valid_from:'2024-01-01',condition:{field:'proposed_gfa_m2',op:'gte',value:20000}},
  {id:'license',status:'CONFIRMED',rule_code:'LICENSE_GATE',priority:100,valid_from:'2024-01-01',condition:{},legal_effect:'PROCEDURAL'},
];
const deps=[{rule_id:'license',depends_on_rule_id:'eiv',dependency_type:'REQUIRES',status:'CONFIRMED'}];
let r=runtime.evaluateRuleGraph(rules,deps,{zone_code:'ZEU',operation_code:'OUC',lot_area_m2:1000,proposed_gfa_m2:25000},'2026-01-01');
assert(r.selected.some(x=>x.id==='ca-special'));
assert(!r.selected.some(x=>x.id==='ca-base'));
assert(r.selected.some(x=>x.id==='eiv'));
assert(r.selected.some(x=>x.id==='license'));
assert.equal(r.calculated.find(x=>x.ruleId==='ca-special').result.value,4000);

// REQUIRES blocks a downstream rule when the prerequisite is not applicable.
r=runtime.evaluateRuleGraph(rules,deps,{zone_code:'ZEU',operation_code:'OUC',lot_area_m2:1000,proposed_gfa_m2:1000},'2026-01-01');
assert(!r.selected.some(x=>x.id==='license'));
assert(r.blocked.some(x=>x.rule.id==='license'&&x.reason==='required_rule_not_applicable'));

// Same-precedence contradictory confirmed rules are surfaced as conflict, never arbitrarily chosen.
const conflict=[
  {id:'h1',status:'CONFIRMED',rule_code:'HEIGHT_MAX',priority:50,condition:{},value_numeric:28,unit:'m'},
  {id:'h2',status:'CONFIRMED',rule_code:'HEIGHT_MAX',priority:50,condition:{},value_numeric:48,unit:'m'},
];
r=runtime.evaluateRuleGraph(conflict,[],{},'2026-01-01');
assert.equal(r.selected.length,0);
assert.equal(r.conflicts[0].kind,'SAME_PRECEDENCE');

// Explicit legal graph overrides are honored only while both rules are confirmed/effective/applicable.
const override=[
  {id:'old',status:'CONFIRMED',rule_code:'PARKING_MIN',priority:100,valid_from:'2020-01-01',condition:{},value_numeric:2},
  {id:'new',status:'CONFIRMED',rule_code:'PARKING_MIN_NEW',priority:100,valid_from:'2024-01-01',condition:{},value_numeric:1},
];
r=runtime.evaluateRuleGraph(override,[{rule_id:'new',depends_on_rule_id:'old',dependency_type:'OVERRIDES',status:'CONFIRMED'}],{},'2026-01-01');
assert(r.selected.some(x=>x.id==='new'));assert(!r.selected.some(x=>x.id==='old'));

console.log('v20 deterministic rule runtime OK');
