const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ld-core-legal-golden-v20-'));
for(const name of ['rule-evaluator','rule-runtime','urban-viability']){
  const src=fs.readFileSync(path.join(root,'services/platform-api/src/territorial',`${name}.ts`),'utf8');
  const out=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
  fs.writeFileSync(path.join(tmp,`${name}.js`),out);
}

const runtime=require(path.join(tmp,'rule-runtime.js'));
const viability=require(path.join(tmp,'urban-viability.js'));
const corpus=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/core-legal-golden-v20.json'),'utf8'));

assert.equal(corpus.truthClass,'SYNTHETIC_RULE_ENGINE');
assert.equal(corpus.municipalTruth,false);
assert(Array.isArray(corpus.cases)&&corpus.cases.length>=9);

function mapChecks(result){return new Map(result.checks.map(x=>[x.code,x]));}
function mapValues(items){return new Map(items.map(x=>[x.code,x.value]));}
function sorted(values){return [...values].sort();}

for(const testCase of corpus.cases){
  const graph=runtime.evaluateRuleGraph(testCase.rules,testCase.dependencies||[],testCase.context,testCase.asOf);
  const result=viability.buildUrbanViability(graph,testCase.context);
  const expected=testCase.expected||{};

  assert.equal(result.status,expected.status,`${testCase.id}: viability status`);
  assert.deepEqual(sorted(graph.selected.map(x=>x.id)),sorted(expected.selectedRuleIds||[]),`${testCase.id}: selected rules`);

  const checks=mapChecks(result);
  for(const [code,status] of Object.entries(expected.checks||{})){
    assert(checks.has(code),`${testCase.id}: missing check ${code}`);
    assert.equal(checks.get(code).status,status,`${testCase.id}: check ${code}`);
  }

  const obligations=mapValues(result.obligations);
  for(const [code,value] of Object.entries(expected.obligations||{})){
    assert(obligations.has(code),`${testCase.id}: missing obligation ${code}`);
    assert.equal(obligations.get(code),value,`${testCase.id}: obligation ${code}`);
  }

  const calculations=mapValues(result.calculations);
  for(const [code,value] of Object.entries(expected.calculations||{})){
    assert(calculations.has(code),`${testCase.id}: missing calculation ${code}`);
    assert.equal(calculations.get(code),value,`${testCase.id}: calculation ${code}`);
  }

  if(expected.conflictRuleIds){
    assert.deepEqual(sorted(result.conflictRuleIds),sorted(expected.conflictRuleIds),`${testCase.id}: conflicts`);
  }
  if(expected.ignoredRuleIds){
    const ignored=graph.trace.filter(x=>x.state==='IGNORED').map(x=>x.ruleId);
    assert.deepEqual(sorted(ignored),sorted(expected.ignoredRuleIds),`${testCase.id}: ignored rules`);
  }
  if(expected.outOfTimeRuleIds){
    const outOfTime=graph.trace.filter(x=>x.state==='OUT_OF_TIME').map(x=>x.ruleId);
    assert.deepEqual(sorted(outOfTime),sorted(expected.outOfTimeRuleIds),`${testCase.id}: effective dates`);
  }

  for(const selected of graph.selected){
    assert.equal(selected.status,'CONFIRMED',`${testCase.id}: non-confirmed rule selected`);
  }
}

console.log(`v20 core/legal golden corpus OK (${corpus.cases.length} cases)`);
