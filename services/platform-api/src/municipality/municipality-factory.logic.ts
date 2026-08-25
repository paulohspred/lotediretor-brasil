import {createHash} from 'node:crypto';
import {isIP} from 'node:net';

export const MUNICIPALITY_FACTORY_VERSION='municipality-factory-v20.1';
export const FACTORY_ADAPTERS=['WFS','WMS','ARCGIS','CKAN','HTML','PDF','ZIP'] as const;
export type FactoryAdapter=typeof FACTORY_ADAPTERS[number];
export type MediaClass='GIS'|'DOCUMENT'|'MIXED';

export function sha256Hex(input:Buffer|string){return createHash('sha256').update(input).digest('hex');}
export function parseAllowedHosts(raw:string|undefined){return [...new Set(String(raw||'').split(',').map(x=>x.trim().toLowerCase()).filter(Boolean))].sort();}
export function isHostAllowed(host:string,allowed:string[]){const h=host.toLowerCase().replace(/\.$/,'');return allowed.some(a=>h===a||h.endsWith('.'+a));}
export function validateFactoryUrl(raw:string,allowedHosts:string[]){
  let u:URL;try{u=new URL(raw);}catch{throw new Error('factory_url_invalid');}
  if(!['http:','https:'].includes(u.protocol))throw new Error('factory_url_protocol_not_allowed');
  const host=u.hostname.toLowerCase();
  if(host==='localhost'||host.endsWith('.localhost')||host.endsWith('.local')||isIP(host)!==0)throw new Error('factory_url_private_or_literal_host_blocked');
  if(!allowedHosts.length)throw new Error('factory_host_allowlist_empty');
  if(!isHostAllowed(host,allowedHosts))throw new Error('factory_host_not_allowlisted');
  u.username='';u.password='';return u;
}

export function detectAdapter(raw:string,hint?:string):FactoryAdapter{
  const h=String(hint||'').toUpperCase();if((FACTORY_ADAPTERS as readonly string[]).includes(h))return h as FactoryAdapter;
  const u=new URL(raw);const path=u.pathname.toLowerCase(),service=String(u.searchParams.get('service')||'').toUpperCase();
  if(service==='WFS')return 'WFS';if(service==='WMS')return 'WMS';
  if(/\/(featureserver|mapserver)(\/\d+)?\/?$/i.test(u.pathname))return 'ARCGIS';
  if(path.includes('/api/3/action/')||path.includes('/dataset/'))return 'CKAN';
  if(path.endsWith('.pdf'))return 'PDF';if(path.endsWith('.zip'))return 'ZIP';return 'HTML';
}

export function requiredPinnedFields(adapter:FactoryAdapter){
  switch(adapter){
    case 'WFS':return ['typeName','srsName'];
    case 'WMS':return ['layers','bbox','crs','width','height','format'];
    case 'ARCGIS':return ['layerId'];
    case 'CKAN':return ['resourceUrl'];
    case 'HTML':return ['parserProfile'];
    case 'PDF':return ['parserProfile'];
    case 'ZIP':return ['archiveProfile'];
  }
}
export function missingPinnedFields(adapter:FactoryAdapter,config:any){return requiredPinnedFields(adapter).filter(k=>config?.[k]===undefined||config?.[k]===null||String(config?.[k]).trim()==='');}

function withParams(base:URL,params:Record<string,string|number>){const u=new URL(base.toString());for(const [k,v] of Object.entries(params))u.searchParams.set(k,String(v));return u;}
export function buildDiscoveryUrl(adapter:FactoryAdapter,base:URL){
  if(adapter==='WFS')return withParams(base,{service:'WFS',request:'GetCapabilities'});
  if(adapter==='WMS')return withParams(base,{service:'WMS',request:'GetCapabilities'});
  if(adapter==='ARCGIS')return withParams(base,{f:'pjson'});
  if(adapter==='CKAN')return base;
  return base;
}
export function buildIngestUrl(adapter:FactoryAdapter,base:URL,config:any){
  if(adapter==='WFS')return withParams(base,{service:'WFS',version:String(config.version||'2.0.0'),request:'GetFeature',typeNames:String(config.typeName),outputFormat:String(config.outputFormat||'application/json'),srsName:String(config.srsName),count:Number(config.pageSize||5000),startIndex:Number(config.startIndex||0)});
  if(adapter==='WMS')return withParams(base,{service:'WMS',version:String(config.version||'1.3.0'),request:'GetMap',layers:String(config.layers),bbox:Array.isArray(config.bbox)?config.bbox.join(','):String(config.bbox),crs:String(config.crs),width:Number(config.width),height:Number(config.height),format:String(config.format),styles:String(config.styles||'')});
  if(adapter==='ARCGIS'){
    const u=new URL(base.toString());const layer=String(config.layerId);if(!new RegExp(`/(FeatureServer|MapServer)/${layer}/?$`,'i').test(u.pathname))u.pathname=u.pathname.replace(/\/$/,'')+'/'+layer+'/query';else u.pathname=u.pathname.replace(/\/$/,'')+'/query';
    return withParams(u,{where:String(config.where||'1=1'),outFields:String(config.outFields||'*'),returnGeometry:String(config.returnGeometry??true),f:String(config.format||'geojson'),resultOffset:Number(config.resultOffset||0),resultRecordCount:Number(config.pageSize||5000),outSR:Number(config.outSR||4326)});
  }
  if(adapter==='CKAN')return new URL(String(config.resourceUrl));
  return base;
}

function xmlNames(text:string){return [...text.matchAll(/<Name>([^<]{1,300})<\/Name>/g)].slice(0,200).map(m=>m[1].trim());}
export function inspectDiscoveryPayload(adapter:FactoryAdapter,httpStatus:number,contentType:string,bytes:Buffer){
  const text=bytes.subarray(0,2_000_000).toString('utf8');const metadata:any={adapter,httpStatus,contentType,byteSample:bytes.length};let valid=httpStatus>=200&&httpStatus<300;
  try{
    if(adapter==='WFS'){valid=valid&&/WFS_Capabilities|FeatureTypeList/i.test(text);metadata.typeNames=xmlNames(text);}
    else if(adapter==='WMS'){valid=valid&&/(WMS_Capabilities|WMT_MS_Capabilities)/i.test(text);metadata.layers=xmlNames(text);}
    else if(adapter==='ARCGIS'){const j=JSON.parse(text);valid=valid&&!j.error&&(j.currentVersion!==undefined||j.layers!==undefined||j.type!==undefined);metadata.currentVersion=j.currentVersion;metadata.layers=Array.isArray(j.layers)?j.layers.slice(0,200).map((x:any)=>({id:x.id,name:x.name})):[];metadata.capabilities=j.capabilities;}
    else if(adapter==='CKAN'){const j=JSON.parse(text);valid=valid&&j.success===true;metadata.resultType=Array.isArray(j.result)?'array':typeof j.result;metadata.resources=Array.isArray(j.result?.resources)?j.result.resources.slice(0,200).map((x:any)=>({id:x.id,name:x.name,format:x.format,url:x.url})):[];}
    else if(adapter==='HTML'){valid=valid&&/<html|<!doctype html/i.test(text);metadata.title=(text.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1]||'').replace(/\s+/g,' ').trim().slice(0,300);}
    else if(adapter==='PDF'){valid=valid&&bytes.subarray(0,5).toString('ascii')==='%PDF-';metadata.magic='PDF';}
    else if(adapter==='ZIP'){valid=valid&&bytes.length>=4&&bytes[0]===0x50&&bytes[1]===0x4b&&[0x03,0x05,0x07].includes(bytes[2]);metadata.magic=valid?'ZIP':'UNKNOWN';}
  }catch(e:any){valid=false;metadata.parseError=String(e?.message||e).slice(0,500);}
  return{status:valid?'PASS':'FAIL',metadata};
}

export function activationGate(input:{adapter:FactoryAdapter;licenseStatus:string;discoveryStatus:string;contractId?:string|null;pinnedConfig:any}){
  const reasons:string[]=[];if(input.licenseStatus!=='VERIFIED')reasons.push('LICENSE_NOT_VERIFIED');if(input.discoveryStatus!=='PASS')reasons.push('DISCOVERY_NOT_PASS');if(!input.contractId)reasons.push('CONTRACT_REQUIRED');for(const f of missingPinnedFields(input.adapter,input.pinnedConfig))reasons.push(`PIN_REQUIRED:${f}`);return{status:reasons.length?'BLOCKED':'READY',reasons};
}
export function requiredQaKinds(mediaClass:MediaClass){return mediaClass==='GIS'?['GIS','STRUCTURE','LICENSE','TEMPORAL']:mediaClass==='DOCUMENT'?['LEGAL','STRUCTURE','LICENSE','TEMPORAL']:['GIS','LEGAL','STRUCTURE','LICENSE','TEMPORAL'];}
export function homologationGate(input:{mediaClass:MediaClass;connectorStatus:string;licenseStatus:string;ingestStatus:string;qa:Record<string,string>;goldenStatus:string;approvedProfessionalGoldens:number;reviewer?:string;reason?:string}){
  const reasons:string[]=[];if(input.connectorStatus!=='ACTIVE')reasons.push('CONNECTOR_NOT_ACTIVE');if(input.licenseStatus!=='VERIFIED')reasons.push('LICENSE_NOT_VERIFIED');if(input.ingestStatus!=='SUCCEEDED')reasons.push('INGEST_NOT_SUCCEEDED');for(const q of requiredQaKinds(input.mediaClass))if(input.qa[q]!=='PASS')reasons.push(`QA_NOT_PASS:${q}`);if(input.goldenStatus!=='PASS')reasons.push('GOLDEN_NOT_PASS');if(input.approvedProfessionalGoldens<1)reasons.push('PROFESSIONAL_GOLDEN_REQUIRED');if(!String(input.reviewer||'').trim())reasons.push('HUMAN_REVIEWER_REQUIRED');if(!String(input.reason||'').trim())reasons.push('REVIEW_REASON_REQUIRED');return{status:reasons.length?'BLOCKED':'READY_FOR_HOMOLOGATION',reasons};
}

export function qaFromNormalized(input:{mediaClass:MediaClass;licenseVerified:boolean;baseDate?:string|null;sourceDate?:string|null;featureCount?:number|null;invalidGeometryCount?:number|null;unknownCrs?:boolean;documentPages?:number|null;citations?:number|null;structureOk:boolean}){
  const checks:Record<string,{status:'PASS'|'WARN'|'FAIL';value?:any}>={};
  checks.LICENSE={status:input.licenseVerified?'PASS':'FAIL'};
  checks.STRUCTURE={status:input.structureOk?'PASS':'FAIL'};
  checks.TEMPORAL={status:input.baseDate&&input.sourceDate?'PASS':'FAIL',value:{baseDate:input.baseDate,sourceDate:input.sourceDate}};
  if(input.mediaClass!=='DOCUMENT')checks.GIS={status:!input.unknownCrs&&Number(input.featureCount||0)>0&&Number(input.invalidGeometryCount||0)===0?'PASS':'FAIL',value:{featureCount:input.featureCount,invalidGeometryCount:input.invalidGeometryCount,unknownCrs:input.unknownCrs}};
  if(input.mediaClass!=='GIS')checks.LEGAL={status:Number(input.documentPages||0)>0&&Number(input.citations||0)>0?'PASS':'FAIL',value:{documentPages:input.documentPages,citations:input.citations}};
  return checks;
}

export function monitorChange(previous:{sha256?:string|null;schemaFingerprint?:string|null;available?:boolean;licenseFingerprint?:string|null}|null,current:{sha256?:string|null;schemaFingerprint?:string|null;available:boolean;licenseFingerprint?:string|null}){
  if(!current.available)return{changeKind:'ENDPOINT_DOWN',severity:'BLOCKING'};
  if(previous&&!previous.available&&current.available)return{changeKind:'ENDPOINT_RECOVERED',severity:'WARN'};
  if(previous?.licenseFingerprint&&current.licenseFingerprint&&previous.licenseFingerprint!==current.licenseFingerprint)return{changeKind:'LICENSE_CHANGED',severity:'BLOCKING'};
  if(previous?.schemaFingerprint&&current.schemaFingerprint&&previous.schemaFingerprint!==current.schemaFingerprint)return{changeKind:'SCHEMA_CHANGED',severity:'BLOCKING'};
  if(previous?.sha256&&current.sha256&&previous.sha256!==current.sha256)return{changeKind:'CONTENT_CHANGED',severity:'WARN'};
  return{changeKind:'UNCHANGED',severity:'INFO'};
}

export function goldenRun(cases:Array<{caseKey:string;expected:any;actual:any;professionalReviewStatus:string}>){
  const results=cases.map(c=>({caseKey:c.caseKey,professionalReviewStatus:c.professionalReviewStatus,pass:c.professionalReviewStatus==='APPROVED'&&JSON.stringify(c.actual)===JSON.stringify(c.expected)}));const passed=results.filter(r=>r.pass).length;return{status:results.length>0&&passed===results.length?'PASS':'FAIL',totalCases:results.length,passedCases:passed,results};
}
