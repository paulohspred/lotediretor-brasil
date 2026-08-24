const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ld-spatial-context-v20-'));
const src=fs.readFileSync(path.join(root,'services/platform-api/src/territorial/spatial-context.ts'),'utf8');
const out=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;
fs.writeFileSync(path.join(tmp,'spatial-context.js'),out);
const {deriveSpatialRuleContext}=require(path.join(tmp,'spatial-context.js'));

let result=deriveSpatialRuleContext([]);
assert.deepEqual(result.context,{});
assert.equal(result.evidence.length,0);
assert.equal(Object.prototype.hasOwnProperty.call(result.context,'heritage_overlap'),false);

result=deriveSpatialRuleContext([
  {feature_id:'h1',layer_code:'IPHAN_BUFFER',domain:'HERITAGE',intersection_area_m2:20,attributes:{}},
  {feature_id:'e1',layer_code:'UTILITY_EASEMENT',domain:'INFRA',intersection_area_m2:80,attributes:{tipo:'servidão'}},
  {feature_id:'e2',layer_code:'FAIXA_SERVIDAO',domain:'INFRA',intersection_area_m2:20,attributes:{}},
  {feature_id:'r1',layer_code:'ROAD_WIDENING',domain:'MOBILITY',intersection_area_m2:35,attributes:{tipo:'melhoramento viário'}},
  {feature_id:'a1',layer_code:'DECEA_PBZPA',domain:'LICENSING',intersection_area_m2:1000,attributes:{height_limit_m:72}},
  {feature_id:'a2',layer_code:'AERODROME_AIRSPACE',domain:'LICENSING',intersection_area_m2:1000,attributes:{altura_max_m:55}},
  {feature_id:'v1',layer_code:'ROAD_ALIGNMENT',domain:'MOBILITY',intersection_area_m2:5,attributes:{largura_via_m:18}},
  {feature_id:'v2',layer_code:'ROAD_OFFICIAL',domain:'MOBILITY',intersection_area_m2:5,attributes:{width_m:24}},
]);
assert.equal(result.context.heritage_overlap,true);
assert.equal(result.context.easement_overlap_m2,100);
assert.equal(result.context.road_widening_area_m2,35);
assert.equal(result.context.aerodrome_limit_m,55);
assert.equal(result.context.road_width_m,24);
assert(result.evidence.some(x=>x.field==='heritage_overlap'&&x.featureIds.includes('h1')));
assert(result.evidence.some(x=>x.field==='aerodrome_limit_m'&&x.value===55));

result=deriveSpatialRuleContext([{feature_id:'x',layer_code:'UNRELATED',domain:'ENVIRONMENT',intersection_area_m2:0,attributes:{}}]);
assert.deepEqual(result.context,{});

console.log('v20 positive spatial context derivation OK');
