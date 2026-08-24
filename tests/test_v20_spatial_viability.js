const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ld-spatial-viability-v20-'));
for(const name of ['rule-evaluator','rule-runtime','urban-viability']){
  const src=fs.readFileSync(path.join(root,'services/platform-api/src/territorial',`${name}.ts`),'utf8');
  const out=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;
  fs.writeFileSync(path.join(tmp,`${name}.js`),out);
}
const runtime=require(path.join(tmp,'rule-runtime.js'));
const viability=require(path.join(tmp,'urban-viability.js'));
const use={id:'use',status:'CONFIRMED',rule_code:'USE_PERMISSION',value_text:'PERMITTED',hard_constraint:true,priority:1,condition:{field:'proposed_use',op:'eq',value:'RESIDENTIAL'}};
const run=(rules,ctx)=>viability.buildUrbanViability(runtime.evaluateRuleGraph([use,...rules],[],ctx,'2026-01-01'),ctx);

let result=run([{id:'air',status:'CONFIRMED',rule_code:'AERODROME_HEIGHT_MAX_M',value_numeric:100,unit:'m',hard_constraint:true,priority:2}],{proposed_use:'RESIDENTIAL',lot_area_m2:1000,height_m:60,aerodrome_limit_m:55});
assert.equal(result.status,'PROHIBITED');
assert(result.checks.some(x=>x.code==='AERODROME_HEIGHT_MAX_M'&&x.required===55&&x.actual===60&&x.status==='FAIL'));

result=run([{id:'heritage',status:'CONFIRMED',rule_code:'HERITAGE_RESTRICTION',value_text:'CONDITIONED',legal_effect:'PROCEDURAL',hard_constraint:true,priority:2}],{proposed_use:'RESIDENTIAL',lot_area_m2:1000,heritage_overlap:true});
assert.equal(result.status,'CONDITIONED');
assert(result.checks.some(x=>x.code==='HERITAGE_RESTRICTION'&&x.status==='CONDITION'));

result=run([{id:'heritage',status:'CONFIRMED',rule_code:'HERITAGE_RESTRICTION',value_text:'CONDITIONED',legal_effect:'PROCEDURAL',hard_constraint:true,priority:2}],{proposed_use:'RESIDENTIAL',lot_area_m2:1000});
assert.equal(result.status,'UNKNOWN');
assert(result.checks.some(x=>x.code==='HERITAGE_RESTRICTION'&&x.status==='UNKNOWN'));

result=run([{id:'easement',status:'CONFIRMED',rule_code:'EASEMENT_NO_BUILD',value_text:'PROHIBITED',hard_constraint:true,priority:2}],{proposed_use:'RESIDENTIAL',lot_area_m2:1000,easement_overlap_m2:12});
assert.equal(result.status,'PROHIBITED');
assert(result.checks.some(x=>x.code==='EASEMENT_NO_BUILD'&&x.status==='FAIL'));

result=run([{id:'widen',status:'CONFIRMED',rule_code:'ROAD_WIDENING_RESTRICTION',value_text:'CONDITIONED',legal_effect:'PROCEDURAL',hard_constraint:true,priority:2}],{proposed_use:'RESIDENTIAL',lot_area_m2:1000,road_widening_area_m2:45});
assert.equal(result.status,'CONDITIONED');
assert(result.obligations.some(x=>x.code==='ROAD_WIDENING_RESERVE'&&x.value===45));

console.log('v20 spatial legal viability constraints OK');
