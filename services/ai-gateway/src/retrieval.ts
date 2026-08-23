import {embedText,embeddingsConfigured} from './embeddings.js';

export type RetrievalScope={
  domains?:string[];scopeId?:string;municipalityIbge?:string;documentIds?:string[];topK?:number;baseDate?:string;
  includePublic?:boolean;knowledgeStatuses?:string[];visibility?:string[];knowledgeAt?:string
};
type Hit={id:string;score:number;text:string;title?:string|null;locator?:string|null;domain?:string|null;documentId?:string|null;documentVersionId?:string|null;sourceSnapshotId?:string|null;metadata?:any;visibility?:string|null;knowledgeStatus?:string|null;pageNumber?:number|null;sectionId?:string|null;recordedAt?:string|null;supersededAt?:string|null;source:'lexical'|'vector'};

function osBase(){return String(process.env.OPENSEARCH_URL||'').replace(/\/$/,'');}
function index(){return String(process.env.OPENSEARCH_EVIDENCE_INDEX||'lotediretor-evidence-v3');}
function headers(){const h:any={'content-type':'application/json'};const u=process.env.OPENSEARCH_USERNAME||'',p=process.env.OPENSEARCH_PASSWORD||'';if(u||p)h.authorization=`Basic ${Buffer.from(`${u}:${p}`).toString('base64')}`;return h;}
export function retrievalConfigured(){return Boolean(osBase());}

function filterClauses(tenantId:string,scope:RetrievalScope){
  const f:any[]=[{term:{retrieval_allowed:true}}];
  const domains=(scope.domains||[]).map(String).filter(Boolean);
  if(domains.length)f.push({terms:{domain:domains}});
  const includePublic=scope.includePublic===true||(scope.includePublic!==false&&Boolean(scope.municipalityIbge));
  if(includePublic&&!scope.municipalityIbge&&!scope.documentIds?.length)throw new Error('municipalityIbge_or_documentIds_required_for_public_retrieval');
  const accessShould:any[]=[{term:{tenant_id:tenantId}}];if(includePublic)accessShould.push({term:{visibility:'PUBLIC'}});
  f.push({bool:{should:accessShould,minimum_should_match:1}});
  if(scope.scopeId)f.push({term:{scope_id:String(scope.scopeId)}});
  if(scope.municipalityIbge)f.push({term:{municipality_ibge:String(scope.municipalityIbge)}});
  const docs=(scope.documentIds||[]).map(String).filter(Boolean);if(docs.length)f.push({terms:{document_id:docs}});
  const statuses=(scope.knowledgeStatuses||[]).map(x=>String(x).toUpperCase()).filter(Boolean);if(statuses.length)f.push({terms:{knowledge_status:statuses}});
  const visibility=(scope.visibility||[]).map(x=>String(x).toUpperCase()).filter(Boolean);if(visibility.length)f.push({terms:{visibility}});
  const knowledgeAt=scope.knowledgeAt?String(scope.knowledgeAt):new Date().toISOString();if(Number.isNaN(Date.parse(knowledgeAt)))throw new Error('knowledgeAt_must_be_ISO8601');
  f.push({bool:{should:[{range:{recorded_at:{lte:knowledgeAt}}},{bool:{must_not:[{exists:{field:'recorded_at'}}]}}],minimum_should_match:1}});
  f.push({bool:{should:[{range:{superseded_at:{gt:knowledgeAt}}},{bool:{must_not:[{exists:{field:'superseded_at'}}]}}],minimum_should_match:1}});
  if(scope.baseDate){
    const day=String(scope.baseDate);if(!/^\d{4}-\d{2}-\d{2}$/.test(day))throw new Error('baseDate_must_be_YYYY_MM_DD');const at=`${day}T12:00:00Z`;
    f.push({bool:{should:[{range:{valid_from:{lte:at}}},{bool:{must_not:[{exists:{field:'valid_from'}}]}}],minimum_should_match:1}});
    f.push({bool:{should:[{range:{valid_to:{gt:at}}},{bool:{must_not:[{exists:{field:'valid_to'}}]}}],minimum_should_match:1}});
  }
  return f;
}

const SOURCE_FIELDS=['tenant_id','domain','document_id','document_version_id','source_snapshot_id','scope_id','municipality_ibge','visibility','knowledge_status','text','title','locator','page_number','section_id','recorded_at','superseded_at','metadata'];
function mapHits(raw:any,source:'lexical'|'vector'):Hit[]{return (raw?.hits?.hits||[]).map((h:any)=>({id:String(h._id),score:Number(h._score||0),text:String(h._source?.text||''),title:h._source?.title||null,locator:h._source?.locator||null,domain:h._source?.domain||null,documentId:h._source?.document_id||null,documentVersionId:h._source?.document_version_id||null,sourceSnapshotId:h._source?.source_snapshot_id||null,visibility:h._source?.visibility||null,knowledgeStatus:h._source?.knowledge_status||null,pageNumber:h._source?.page_number??null,sectionId:h._source?.section_id||null,recordedAt:h._source?.recorded_at||null,supersededAt:h._source?.superseded_at||null,metadata:h._source?.metadata||{},source})).filter((h:Hit)=>h.text);}

async function postSearch(body:any){const r=await fetch(`${osBase()}/${encodeURIComponent(index())}/_search`,{method:'POST',headers:headers(),body:JSON.stringify(body)});const raw:any=await r.json().catch(()=>({}));if(!r.ok)throw new Error(`opensearch_${r.status}_${String(raw?.error?.reason||raw?.error?.type||'search_failed')}`);return raw;}

async function lexical(tenantId:string,question:string,scope:RetrievalScope,k:number){
  const body={size:k,track_total_hits:false,_source:SOURCE_FIELDS,query:{bool:{filter:filterClauses(tenantId,scope),must:[{multi_match:{query:question,fields:['text^3','title^2','locator','section_id'],type:'best_fields',operator:'or',minimum_should_match:'25%'}}]}}};
  return mapHits(await postSearch(body),'lexical');
}
async function vector(tenantId:string,question:string,scope:RetrievalScope,k:number){
  const emb=await embedText(question);if(!emb)return[];
  const body={size:k,track_total_hits:false,_source:SOURCE_FIELDS,query:{bool:{filter:filterClauses(tenantId,scope),must:[{knn:{embedding:{vector:emb.vector,k,method_parameters:{ef_search:Math.max(64,k*8)}}}}]}}};
  return mapHits(await postSearch(body),'vector');
}
function rrf(lists:Hit[][],k=60){const scores=new Map<string,{hit:Hit;score:number;sources:Set<string>}>();for(const list of lists){list.forEach((hit,rank)=>{const current=scores.get(hit.id)||{hit,score:0,sources:new Set<string>()};current.score+=1/(k+rank+1);current.sources.add(hit.source);scores.set(hit.id,current);});}return [...scores.values()].sort((a,b)=>b.score-a.score).map(x=>({...x.hit,rrfScore:x.score,retrievalSources:[...x.sources]}));}
function terms(text:string){return [...new Set(text.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').split(/[^a-z0-9]+/).filter(x=>x.length>=3&&!['para','com','uma','que','dos','das','por','sobre','qual','quais'].includes(x)))];}
function exactLegalBoost(question:string,item:any){const q=question.toLowerCase();const hay=`${item.title||''} ${item.locator||''} ${item.sectionId||''} ${item.text||''}`.toLowerCase();let boost=0;const legalTokens=q.match(/(?:lei\s*)?\d{1,6}(?:[.\/]\d{2,4})?|art\.?\s*\d+[a-zº°-]*/gi)||[];for(const token of legalTokens)if(hay.includes(token.toLowerCase()))boost+=0.02;return Math.min(boost,0.08);}
function rerank(question:string,items:any[]){const q=terms(question);return items.map(x=>{const h=new Set(terms(`${x.title||''} ${x.text||''}`));const matched=q.filter(t=>h.has(t)).length;const coverage=q.length?matched/q.length:0;const legalBoost=exactLegalBoost(question,x);return{...x,termCoverage:coverage,legalExactBoost:legalBoost,rerankScore:Number(x.rrfScore||0)+(coverage*0.01)+legalBoost}}).sort((a,b)=>b.rerankScore-a.rerankScore);}

export async function retrieveEvidence(tenantId:string,question:string,scope:RetrievalScope={}){
  if(!retrievalConfigured()||!tenantId||!question.trim())return{mode:'disabled',items:[],lexicalCount:0,vectorCount:0,embeddingsConfigured:embeddingsConfigured()};
  const topK=Math.max(1,Math.min(Number(scope.topK||12),30));let lexicalHits:Hit[]=[];let vectorHits:Hit[]=[];const errors:string[]=[];
  try{lexicalHits=await lexical(tenantId,question,scope,Math.max(topK,20));}catch(e:any){errors.push(`lexical:${e?.message||e}`);}
  if(embeddingsConfigured())try{vectorHits=await vector(tenantId,question,scope,Math.max(topK,20));}catch(e:any){errors.push(`vector:${e?.message||e}`);}
  const fused=rerank(question,rrf([lexicalHits,vectorHits])).slice(0,topK);
  return{mode:vectorHits.length?'hybrid_rrf_legal_rerank':'lexical_legal_rerank',items:fused,lexicalCount:lexicalHits.length,vectorCount:vectorHits.length,embeddingsConfigured:embeddingsConfigured(),baseDate:scope.baseDate||null,knowledgeAt:scope.knowledgeAt||null,publicIncluded:scope.includePublic===true||(scope.includePublic!==false&&Boolean(scope.municipalityIbge)),errors};
}
