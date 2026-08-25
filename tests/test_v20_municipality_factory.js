const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');
const root=path.resolve(__dirname,'..');
const src=fs.readFileSync(path.join(root,'services/platform-api/src/municipality/municipality-factory.logic.ts'),'utf8');
const out=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true},reportDiagnostics:true});
assert.equal((out.diagnostics||[]).filter(x=>x.category===ts.DiagnosticCategory.Error).length,0);
const tmp=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'ld-mf-v20-')),'factory.js');fs.writeFileSync(tmp,out.outputText);const f=require(tmp);
assert.equal(f.MUNICIPALITY_FACTORY_VERSION,'municipality-factory-v20.1');
assert.deepEqual(f.FACTORY_ADAPTERS,['WFS','WMS','ARCGIS','CKAN','HTML','PDF','ZIP']);

const allow=['geo.prefeitura.gov.br','dados.gov.br'];
assert.equal(f.validateFactoryUrl('https://geo.prefeitura.gov.br/geoserver/ows',allow).hostname,'geo.prefeitura.gov.br');
assert.equal(f.validateFactoryUrl('https://sub.geo.prefeitura.gov.br/a',allow).hostname,'sub.geo.prefeitura.gov.br');
for(const bad of ['http://localhost/a','http://127.0.0.1/a','http://169.254.169.254/latest','file:///etc/passwd','https://evil.example/a'])assert.throws(()=>f.validateFactoryUrl(bad,allow));
assert.throws(()=>f.validateFactoryUrl('https://geo.prefeitura.gov.br/a',[]),/allowlist_empty/);

assert.equal(f.detectAdapter('https://geo.prefeitura.gov.br/ows?service=WFS'),'WFS');
assert.equal(f.detectAdapter('https://geo.prefeitura.gov.br/ows?service=WMS'),'WMS');
assert.equal(f.detectAdapter('https://geo.prefeitura.gov.br/arcgis/rest/services/x/FeatureServer'),'ARCGIS');
assert.equal(f.detectAdapter('https://dados.gov.br/api/3/action/package_show?id=x'),'CKAN');
assert.equal(f.detectAdapter('https://geo.prefeitura.gov.br/lei.pdf'),'PDF');
assert.equal(f.detectAdapter('https://geo.prefeitura.gov.br/base.zip'),'ZIP');
assert.equal(f.detectAdapter('https://geo.prefeitura.gov.br/legislacao'),'HTML');

const wfs=f.buildIngestUrl('WFS',new URL('https://geo.prefeitura.gov.br/ows'),{typeName:'parcelas',srsName:'EPSG:4326',pageSize:100,startIndex:200});
assert.equal(wfs.searchParams.get('request'),'GetFeature');assert.equal(wfs.searchParams.get('typeNames'),'parcelas');assert.equal(wfs.searchParams.get('startIndex'),'200');
const arc=f.buildIngestUrl('ARCGIS',new URL('https://geo.prefeitura.gov.br/arcgis/rest/services/lotes/FeatureServer'),{layerId:0,pageSize:500,resultOffset:1000});
assert(arc.pathname.endsWith('/0/query'));assert.equal(arc.searchParams.get('resultOffset'),'1000');

const wfsCap=Buffer.from('<WFS_Capabilities><FeatureTypeList><FeatureType><Name>sp:lote</Name></FeatureType></FeatureTypeList></WFS_Capabilities>');
let inspected=f.inspectDiscoveryPayload('WFS',200,'text/xml',wfsCap);assert.equal(inspected.status,'PASS');assert(inspected.metadata.typeNames.includes('sp:lote'));
const wmsCap=Buffer.from('<WMS_Capabilities><Layer><Name>zoneamento</Name></Layer></WMS_Capabilities>');assert.equal(f.inspectDiscoveryPayload('WMS',200,'text/xml',wmsCap).status,'PASS');
assert.equal(f.inspectDiscoveryPayload('ARCGIS',200,'application/json',Buffer.from(JSON.stringify({currentVersion:11.2,layers:[{id:0,name:'lotes'}]}))).status,'PASS');
assert.equal(f.inspectDiscoveryPayload('CKAN',200,'application/json',Buffer.from(JSON.stringify({success:true,result:{resources:[{id:'r1',format:'SHP',url:'https://dados.gov.br/r.zip'}]}}))).status,'PASS');
assert.equal(f.inspectDiscoveryPayload('HTML',200,'text/html',Buffer.from('<!doctype html><html><title>Lei</title></html>')).status,'PASS');
assert.equal(f.inspectDiscoveryPayload('PDF',200,'application/pdf',Buffer.from('%PDF-1.7\n')).status,'PASS');
assert.equal(f.inspectDiscoveryPayload('ZIP',200,'application/zip',Buffer.from([0x50,0x4b,0x03,0x04,0,0])).status,'PASS');
assert.equal(f.inspectDiscoveryPayload('WFS',500,'text/plain',Buffer.from('error')).status,'FAIL');

let gate=f.activationGate({adapter:'WFS',licenseStatus:'VERIFIED',discoveryStatus:'PASS',contractId:'c1',pinnedConfig:{typeName:'lotes',srsName:'EPSG:4326'}});assert.equal(gate.status,'READY');
gate=f.activationGate({adapter:'WFS',licenseStatus:'UNVERIFIED',discoveryStatus:'PASS',contractId:'c1',pinnedConfig:{}});assert.equal(gate.status,'BLOCKED');assert(gate.reasons.includes('LICENSE_NOT_VERIFIED'));assert(gate.reasons.includes('PIN_REQUIRED:typeName'));

const qa=f.qaFromNormalized({mediaClass:'MIXED',licenseVerified:true,baseDate:'2026-08-25',sourceDate:'2026-08-24',featureCount:10,invalidGeometryCount:0,unknownCrs:false,documentPages:20,citations:4,structureOk:true});
for(const k of ['GIS','LEGAL','STRUCTURE','LICENSE','TEMPORAL'])assert.equal(qa[k].status,'PASS',k);
const h=f.homologationGate({mediaClass:'MIXED',connectorStatus:'ACTIVE',licenseStatus:'VERIFIED',ingestStatus:'SUCCEEDED',qa:Object.fromEntries(Object.entries(qa).map(([k,v])=>[k,v.status])),goldenStatus:'PASS',approvedProfessionalGoldens:1,reviewer:'human',reason:'reviewed'});assert.equal(h.status,'READY_FOR_HOMOLOGATION');
assert.equal(f.homologationGate({mediaClass:'GIS',connectorStatus:'ACTIVE',licenseStatus:'VERIFIED',ingestStatus:'SUCCEEDED',qa:{GIS:'PASS',STRUCTURE:'PASS',LICENSE:'PASS',TEMPORAL:'PASS'},goldenStatus:'PASS',approvedProfessionalGoldens:0,reviewer:'human',reason:'reviewed'}).status,'BLOCKED');

assert.deepEqual(f.monitorChange(null,{sha256:'a',schemaFingerprint:'s',available:false}),{changeKind:'ENDPOINT_DOWN',severity:'BLOCKING'});
assert.equal(f.monitorChange({sha256:'a',schemaFingerprint:'s',available:true,licenseFingerprint:'l1'},{sha256:'a',schemaFingerprint:'s',available:true,licenseFingerprint:'l2'}).changeKind,'LICENSE_CHANGED');
assert.equal(f.monitorChange({sha256:'a',schemaFingerprint:'s',available:true},{sha256:'b',schemaFingerprint:'s',available:true}).changeKind,'CONTENT_CHANGED');
const gr=f.goldenRun([{caseKey:'A',expected:{zone:'Z1'},actual:{zone:'Z1'},professionalReviewStatus:'APPROVED'}]);assert.equal(gr.status,'PASS');assert.equal(gr.passedCases,1);
assert.equal(f.goldenRun([{caseKey:'A',expected:{zone:'Z1'},actual:{zone:'Z1'},professionalReviewStatus:'PENDING'}]).status,'FAIL');
console.log('v20 Municipality Factory connector/QA/golden/homologation logic OK');
