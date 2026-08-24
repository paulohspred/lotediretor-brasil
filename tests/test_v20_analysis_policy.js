const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ld-analysis-policy-v20-'));
const src=fs.readFileSync(path.join(root,'services/platform-api/src/territorial/analysis-decision-policy.ts'),'utf8');
const out=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;
fs.writeFileSync(path.join(tmp,'analysis-decision-policy.js'),out);
const {deriveAnalysisRunStatus}=require(path.join(tmp,'analysis-decision-policy.js'));

const base={viabilityStatus:'PERMITTED',hasRules:true,hasSpatialEvidence:false,legalTemporalConflictCount:0,legalTemporalUnknownCount:0};
assert.equal(deriveAnalysisRunStatus(base),'COMPLETED');
assert.equal(deriveAnalysisRunStatus({...base,viabilityStatus:'CONDITIONED'}),'COMPLETED');
assert.equal(deriveAnalysisRunStatus({...base,viabilityStatus:'PROHIBITED'}),'COMPLETED');
assert.equal(deriveAnalysisRunStatus({...base,viabilityStatus:'UNKNOWN'}),'NEEDS_REVIEW');
assert.equal(deriveAnalysisRunStatus({...base,viabilityStatus:'CONFLICTING'}),'NEEDS_REVIEW');
assert.equal(deriveAnalysisRunStatus({...base,legalTemporalUnknownCount:1}),'NEEDS_REVIEW');
assert.equal(deriveAnalysisRunStatus({...base,legalTemporalConflictCount:1}),'NEEDS_REVIEW');
assert.equal(deriveAnalysisRunStatus({...base,hasRules:false,hasSpatialEvidence:false}),'INSUFFICIENT_DATA');
assert.equal(deriveAnalysisRunStatus({...base,hasRules:false,hasSpatialEvidence:true}),'COMPLETED');

console.log('v20 analysis decision policy OK');
