import {PutObjectCommand,S3Client} from '@aws-sdk/client-s3';
import {buildDiscoveryUrl,buildIngestUrl,expectedOutputCrs,FactoryAdapter,inspectDiscoveryPayload,inspectGeoJsonForQa,sha256Hex,validateFactoryUrl} from './municipality-factory.logic';

export type FactoryFetchResult={status:number;contentType:string;bytes:Buffer;url:string;headers:Record<string,string>};
export type FactoryIngestResult={bytes:Buffer;contentType:string;objectKey:string;sha256:string;byteSize:number;pageCount:number;featureCount:number|null;metadata:any};

function positiveInt(v:any,fallback:number,max:number){const n=Number(v);return Number.isFinite(n)&&n>0?Math.min(Math.floor(n),max):fallback;}
function envAllowedHosts(){return String(process.env.MUNICIPALITY_FACTORY_ALLOWED_HOSTS||'').split(',').map(x=>x.trim().toLowerCase()).filter(Boolean);}
function safeHeaderMap(h:Headers){const keep=['content-type','etag','last-modified','content-length','content-disposition'];const out:Record<string,string>={};for(const k of keep){const v=h.get(k);if(v)out[k]=v.slice(0,1000);}return out;}
function extension(adapter:FactoryAdapter,contentType:string){if(adapter==='PDF')return 'pdf';if(adapter==='ZIP')return 'zip';if(adapter==='HTML')return 'html';if(adapter==='WMS')return contentType.includes('png')?'png':contentType.includes('jpeg')?'jpg':'bin';return 'json';}
function normalizedSourceDate(headers:Record<string,string>){const raw=headers['last-modified'];if(!raw)return null;const ms=Date.parse(raw);return Number.isFinite(ms)?new Date(ms).toISOString():null;}

export async function fetchLimited(rawUrl:string,maxBytes:number,timeoutMs:number):Promise<FactoryFetchResult>{
  const allowed=envAllowedHosts();const u=validateFactoryUrl(rawUrl,allowed);const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{
    const res=await fetch(u,{method:'GET',redirect:'manual',signal:controller.signal,headers:{'user-agent':'LoteDiretor-MunicipalityFactory/20'}});
    if(res.status>=300&&res.status<400)throw new Error('factory_redirect_blocked');
    const declared=Number(res.headers.get('content-length')||0);if(declared>maxBytes)throw new Error('factory_payload_too_large');
    const reader=res.body?.getReader();const chunks:Buffer[]=[];let total=0;
    if(reader){for(;;){const x=await reader.read();if(x.done)break;total+=x.value.byteLength;if(total>maxBytes){await reader.cancel();throw new Error('factory_payload_too_large');}chunks.push(Buffer.from(x.value));}}
    const bytes=Buffer.concat(chunks);return{status:res.status,contentType:String(res.headers.get('content-type')||'application/octet-stream').toLowerCase(),bytes,url:u.toString(),headers:safeHeaderMap(res.headers)};
  }finally{clearTimeout(timer);}
}

export async function discoverSource(adapter:FactoryAdapter,endpointUrl:string){
  const allowed=envAllowedHosts();const endpoint=validateFactoryUrl(endpointUrl,allowed);const url=buildDiscoveryUrl(adapter,endpoint);
  const max=positiveInt(process.env.MUNICIPALITY_FACTORY_DISCOVERY_MAX_BYTES,2_097_152,10_000_000);const timeout=positiveInt(process.env.MUNICIPALITY_FACTORY_FETCH_TIMEOUT_MS,30_000,120_000);
  const fetched=await fetchLimited(url.toString(),max,timeout);const inspected=inspectDiscoveryPayload(adapter,fetched.status,fetched.contentType,fetched.bytes);
  return{...inspected,httpStatus:fetched.status,contentType:fetched.contentType,requestedUrl:endpoint.toString(),resolvedUrl:fetched.url,capabilitySha256:sha256Hex(fetched.bytes),headers:fetched.headers};
}

function mergeGeoJson(parts:FactoryFetchResult[]){
  const features:any[]=[];let crs:any=null;for(const p of parts){const j=JSON.parse(p.bytes.toString('utf8'));if(j.type!=='FeatureCollection'||!Array.isArray(j.features))throw new Error('factory_geojson_featurecollection_required');features.push(...j.features);if(!crs&&j.crs)crs=j.crs;}
  return Buffer.from(JSON.stringify({type:'FeatureCollection',...(crs?{crs}:{}),features}));
}

async function fetchPagedGeoJson(adapter:FactoryAdapter,endpoint:URL,config:any,maxBytes:number,timeoutMs:number,maxPages:number){
  const pageSize=positiveInt(config?.pageSize,5000,10_000);const pages:FactoryFetchResult[]=[];let aggregate=0;let offset=Number(config?.startIndex??config?.resultOffset??0)||0;
  for(let page=0;page<maxPages;page++){
    const cfg={...config,pageSize};if(adapter==='WFS')cfg.startIndex=offset;else cfg.resultOffset=offset;
    const u=buildIngestUrl(adapter,endpoint,cfg);const fetched=await fetchLimited(u.toString(),Math.min(maxBytes-aggregate,maxBytes),timeoutMs);if(fetched.status<200||fetched.status>=300)throw new Error(`factory_ingest_http_${fetched.status}`);
    const json=JSON.parse(fetched.bytes.toString('utf8'));if(json.type!=='FeatureCollection'||!Array.isArray(json.features))throw new Error('factory_geojson_featurecollection_required');
    pages.push(fetched);aggregate+=fetched.bytes.length;if(aggregate>maxBytes)throw new Error('factory_payload_too_large');const count=json.features.length;offset+=count;if(count<pageSize)break;if(count===0)break;
  }
  if(pages.length===maxPages){const last=JSON.parse(pages[pages.length-1].bytes.toString('utf8'));if(last.features.length>=pageSize)throw new Error('factory_max_pages_reached');}
  const bytes=mergeGeoJson(pages);if(bytes.length>maxBytes)throw new Error('factory_payload_too_large');const parsed=JSON.parse(bytes.toString('utf8'));
  return{bytes,contentType:'application/geo+json',pageCount:pages.length,featureCount:parsed.features.length,headers:pages.at(-1)?.headers||{}};
}

function s3Client(){return new S3Client({region:process.env.S3_REGION||'us-east-1',endpoint:process.env.S3_ENDPOINT,forcePathStyle:Boolean(process.env.S3_ENDPOINT),credentials:process.env.S3_ACCESS_KEY&&process.env.S3_SECRET_KEY?{accessKeyId:process.env.S3_ACCESS_KEY,secretAccessKey:process.env.S3_SECRET_KEY}:undefined});}
export async function ingestSource(input:{adapter:FactoryAdapter;endpointUrl:string;pinnedConfig:any;municipalityIbge:string;datasetCode:string;contractCode:string;contractVersion:number}) : Promise<FactoryIngestResult>{
  const allowed=envAllowedHosts();const endpoint=validateFactoryUrl(input.endpointUrl,allowed);const maxBytes=positiveInt(process.env.MUNICIPALITY_FACTORY_MAX_INGEST_BYTES||process.env.MAX_UPLOAD_BYTES,26_214_400,200_000_000);const timeout=positiveInt(process.env.MUNICIPALITY_FACTORY_FETCH_TIMEOUT_MS,30_000,120_000);const maxPages=positiveInt(process.env.MUNICIPALITY_FACTORY_MAX_PAGES,100,500);
  let bytes:Buffer,contentType:string,pageCount=1,featureCount:number|null=null,headers:Record<string,string>={};
  if(input.adapter==='WFS'||input.adapter==='ARCGIS'){
    const r=await fetchPagedGeoJson(input.adapter,endpoint,input.pinnedConfig,maxBytes,timeout,maxPages);bytes=r.bytes;contentType=r.contentType;pageCount=r.pageCount;featureCount=r.featureCount;headers=r.headers;
  }else{
    const u=buildIngestUrl(input.adapter,endpoint,input.pinnedConfig);validateFactoryUrl(u.toString(),allowed);const r=await fetchLimited(u.toString(),maxBytes,timeout);if(r.status<200||r.status>=300)throw new Error(`factory_ingest_http_${r.status}`);bytes=r.bytes;contentType=r.contentType;headers=r.headers;
    if(input.adapter==='CKAN'&&contentType.includes('json')){try{const j=JSON.parse(bytes.toString('utf8'));featureCount=Array.isArray(j?.features)?j.features.length:null;}catch{/* raw resource is retained */}}
  }
  let qaMetadata:any={structureOk:bytes.length>0,outputCrs:null,unknownCrs:false,invalidGeometryCount:null,featureCount};
  if(input.adapter==='WFS'||input.adapter==='ARCGIS'){
    qaMetadata=inspectGeoJsonForQa(bytes,expectedOutputCrs(input.adapter,input.pinnedConfig));
    if(qaMetadata.outputCrs!=='EPSG:4326'||qaMetadata.unknownCrs)throw new Error('factory_output_crs_not_wgs84');
    featureCount=qaMetadata.featureCount;
  }else if(input.adapter==='CKAN'&&contentType.includes('json')){
    try{const parsed=JSON.parse(bytes.toString('utf8'));if(parsed?.type==='FeatureCollection')qaMetadata=inspectGeoJsonForQa(bytes,null);}catch{/* non-GeoJSON CKAN resources stay raw */}
  }else if(input.adapter==='PDF')qaMetadata.structureOk=bytes.subarray(0,5).toString('ascii')==='%PDF-';
  else if(input.adapter==='ZIP')qaMetadata.structureOk=bytes.length>=4&&bytes[0]===0x50&&bytes[1]===0x4b&&[0x03,0x05,0x07].includes(bytes[2]);
  else if(input.adapter==='HTML')qaMetadata.structureOk=/<html|<!doctype html/i.test(bytes.subarray(0,2_000_000).toString('utf8'));
  const sha256=sha256Hex(bytes);const ext=extension(input.adapter,contentType);const objectKey=`municipality-factory/${input.municipalityIbge}/${input.datasetCode}/${sha256}.${ext}`;const bucket=String(process.env.S3_BUCKET||'');if(!bucket)throw new Error('s3_bucket_required');
  await s3Client().send(new PutObjectCommand({Bucket:bucket,Key:objectKey,Body:bytes,ContentType:contentType,Metadata:{sha256,adapter:input.adapter.toLowerCase(),municipality:input.municipalityIbge,dataset:input.datasetCode.toLowerCase()}}));
  return{bytes,contentType,objectKey,sha256,byteSize:bytes.length,pageCount,featureCount,metadata:{factoryVersion:'municipality-factory-v20.1',adapter:input.adapter,contract:{code:input.contractCode,version:input.contractVersion},pinnedConfigFingerprint:sha256Hex(JSON.stringify(input.pinnedConfig||{})),pageCount,featureCount,headers,sourceDate:normalizedSourceDate(headers),...qaMetadata,endpointHost:endpoint.hostname,fetchedAt:new Date().toISOString()}};
}
