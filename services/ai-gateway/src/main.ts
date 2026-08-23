import Fastify from 'fastify';
import {randomUUID} from 'crypto';
import {retrieveEvidence,retrievalConfigured} from './retrieval.js';
import {embeddingsConfigured} from './embeddings.js';
import {prompt,promptRegistry} from './prompts.js';
import {toolRegistry,toolAuthorized} from './tools.js';

const app=Fastify({logger:true});
const VERSION='19.0.0-rc.3';

function internal(req:any,reply:any){const expected=process.env.INTERNAL_API_TOKEN||'';if(!expected||req.headers?.['x-internal-token']!==expected){reply.code(403);return false}return true;}
function route(question:string){const x=question.toLowerCase();if(/condom[ií]nio|conven[cç][aã]o|assembleia|ata|regimento/.test(x))return'condominio';if(/planta|torre|vaga|garagem|implanta[cç][aã]o|arquitet|massa/.test(x))return'ai-tec';return'cidades';}
function riskClass(question:string){const x=question.toLowerCase();if(/pode construir|vi[aá]vel|aprova[cç][aã]o|proibido|permitido|multa|san[cç][aã]o|embargo|demoli[cç][aã]o/.test(x))return'HIGH';if(/regra|lei|artigo|recuo|coeficiente|conven[cç][aã]o|qu[oó]rum/.test(x))return'MEDIUM';return'LOW';}

async function trace(payload:any){const base=process.env.CONTROL_INTERNAL_URL||'http://control-api:3002';const token=process.env.INTERNAL_API_TOKEN||'';if(!token)return;try{await fetch(`${base}/control/internal/v1/ai-traces`,{method:'POST',headers:{'content-type':'application/json','x-internal-token':token},body:JSON.stringify(payload)});}catch(error){app.log.warn({error},'failed to persist ai trace');}}

function confirmedRules(rules:any[]){return rules.filter(r=>{if(String(r?.status||'').toUpperCase()!=='CONFIRMED')return false;const cond=r?.condition&&typeof r.condition==='object'&&!Array.isArray(r.condition)?r.condition:{};if(!Object.keys(cond).length)return true;const ev=String(r?.conditionEvaluation?.status||r?.condition_evaluation?.status||'').toUpperCase();return ev==='MATCH';});}
function deterministicAnswer(assistant:string,rules:any[],evidence:any[]){const confirmed=confirmedRules(rules);if(!confirmed.length)return null;const lines=confirmed.slice(0,20).map(r=>{const value=r.value??r.value_numeric??r.value_text??r.rule_text??'';const unit=r.unit?` ${r.unit}`:'';const source=r.source_locator||r.sourceLocator||r.evidence?.locator||'';return `${r.parameter||r.title||r.rule_type||'Regra'}: ${value}${unit}${source?` [${source}]`:''}`;});return{assistant,answer:lines.join('\n'),mode:'deterministic_confirmed_rules',decision_status:'NAO_DETERMINADO',conditions:[],uncertainty:'MEDIA',missing_information:['Síntese determinística lista regras confirmadas, mas não infere uma conclusão jurídica que não esteja explicitamente computada.'],professional_review:'RECOMENDADA',evidenceCount:evidence.length,ruleCount:confirmed.length,disclaimer:'Resposta limitada às regras CONFIRMED fornecidas no contexto; nenhuma regra ausente foi inferida.'};}

function compactEvidence(evidence:any[]){return evidence.slice(0,30).map((x,i)=>({id:x.id||x.evidenceId||`e${i+1}`,title:x.title||x.documentTitle||null,locator:x.locator||x.sourceLocator||null,text:String(x.text||x.text_content||x.content||'').slice(0,3500),metadata:x.metadata||{}})).filter(x=>x.text||x.locator);}

function providerConfigured(){return Boolean(process.env.AI_CHAT_ENDPOINT||process.env.AI_BASE_URL)&&Boolean(process.env.AI_API_KEY)&&Boolean(process.env.AI_MODEL);}

async function providerAnswer(assistant:string,question:string,evidence:any[],traceId:string){
  const endpoint=process.env.AI_CHAT_ENDPOINT||process.env.AI_BASE_URL||'';const key=process.env.AI_API_KEY||'';const model=process.env.AI_MODEL||'';
  if(!endpoint||!key||!model)return null;
  const compact=compactEvidence(evidence);if(!compact.length)return null;
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),Number(process.env.AI_TIMEOUT_MS||30000));
  try{
    const promptDef=prompt('legal_grounded',{assistant});const system=promptDef.text;
    const r=await fetch(endpoint,{method:'POST',headers:{'content-type':'application/json','authorization':`Bearer ${key}`},signal:controller.signal,body:JSON.stringify({model,messages:[{role:'system',content:system},{role:'user',content:JSON.stringify({question,evidence:compact,trace_id:traceId})}],temperature:0,response_format:{type:'json_object'}})});
    const raw:any=await r.json().catch(()=>({}));if(!r.ok)throw new Error(`provider_http_${r.status}`);
    const content=raw?.choices?.[0]?.message?.content??raw?.output_text??raw?.content;let parsed:any;
    try{parsed=typeof content==='string'?JSON.parse(content):content;}catch{parsed={status:'ABSTAIN',answer:'Resposta do provedor não estava em JSON validável.',evidence_ids:[],limitations:['provider_invalid_json']};}
    const allowed=new Set(compact.map(x=>String(x.id)));const declared=Array.isArray(parsed?.evidence_ids)?parsed.evidence_ids.map(String):[];const invalid=declared.filter((x:string)=>!allowed.has(x));const ids=declared.filter((x:string)=>allowed.has(x));const answer=String(parsed?.answer||'').trim();
    if(invalid.length)return{status:'ABSTAINED',decision_status:'NAO_DETERMINADO',answer:'O provedor citou evidência fora do contexto autorizado.',conditions:[],evidence_ids:ids,uncertainty:'ALTA',missing_information:[],professional_review:'RECOMENDADA',limitations:[...(parsed?.limitations||[]),'provider_invalid_evidence_id']};
    const grounding=String(parsed?.grounding_status||parsed?.status||'').toUpperCase();const decision=String(parsed?.decision_status||'NAO_DETERMINADO').toUpperCase();const allowedDecision=new Set(['PERMITIDO','PROIBIDO','CONDICIONADO','NAO_DETERMINADO','CONFLITO']);
    if(grounding!=='GROUNDED'||!ids.length||!answer)return{status:'ABSTAINED',decision_status:'NAO_DETERMINADO',answer:answer||'Evidência insuficiente.',evidence_ids:ids,conditions:[],uncertainty:'ALTA',missing_information:Array.isArray(parsed?.missing_information)?parsed.missing_information:[],professional_review:'RECOMENDADA',limitations:[...(parsed?.limitations||[]),'provider_grounding_gate_failed']};
    return{status:'GROUNDED',decision_status:allowedDecision.has(decision)?decision:'NAO_DETERMINADO',answer,evidence_ids:ids,conditions:Array.isArray(parsed?.conditions)?parsed.conditions:[],uncertainty:['BAIXA','MEDIA','ALTA'].includes(String(parsed?.uncertainty||'').toUpperCase())?String(parsed.uncertainty).toUpperCase():'MEDIA',missing_information:Array.isArray(parsed?.missing_information)?parsed.missing_information:[],professional_review:['NENHUMA','RECOMENDADA','OBRIGATORIA'].includes(String(parsed?.professional_review||'').toUpperCase())?String(parsed.professional_review).toUpperCase():'RECOMENDADA',limitations:Array.isArray(parsed?.limitations)?parsed.limitations:[],mode:'provider_grounded',prompt_id:promptDef.id,prompt_version:promptDef.version};
  }finally{clearTimeout(timer);}
}

app.get('/ai/health',async()=>({ok:true,service:'ai-gateway',version:VERSION,providerConfigured:providerConfigured(),retrievalConfigured:retrievalConfigured(),embeddingsConfigured:embeddingsConfigured(),evidenceIndex:process.env.OPENSEARCH_EVIDENCE_INDEX||'lotediretor-evidence-v3'}));
app.post('/ai/v1/route',async(req:any,reply:any)=>{if(!internal(req,reply))return{error:'forbidden'};const message=String(req.body?.message||'');return{assistant:route(message),risk_class:riskClass(message),policy:'authorize_retrieve_tools_validate_or_abstain'};});
app.post('/ai/v1/registry',async(req:any,reply:any)=>{if(!internal(req,reply))return{error:'forbidden'};const assistant=String(req.body?.assistant||'');const requested=String(req.body?.toolId||'');const explicit=Boolean(req.body?.explicitUserAction);return{version:VERSION,prompts:promptRegistry(),tools:toolRegistry(assistant||undefined),authorization:requested?toolAuthorized(requested,assistant,explicit):null};});
app.post('/ai/v1/retrieve',async(req:any,reply:any)=>{
  if(!internal(req,reply))return{error:'forbidden'};const body=req.body||{};const tenantId=String(body.tenantId||'');if(!tenantId)return reply.code(400).send({error:'tenantId_required'});const question=String(body.query||body.message||'').slice(0,12000);if(!question.trim())return reply.code(400).send({error:'query_required'});
  const result=await retrieveEvidence(tenantId,question,body.scope||{});return{status:'OK',...result};
});
app.post('/ai/v1/chat',async(req:any,reply:any)=>{
  if(!internal(req,reply))return{error:'forbidden'};
  const started=Date.now();const body=req.body||{};const question=String(body.message||'').slice(0,12000);const assistant=body.assistant||route(question);const risk=riskClass(question);const traceId=randomUUID();const rules=Array.isArray(body.context?.rules)?body.context.rules.slice(0,100):[];const contextEvidence=Array.isArray(body.context?.evidence)?body.context.evidence.slice(0,100):[];
  let retrieval:any={mode:'not_requested',items:[]};
  if(body.retrieval?.enabled&&body.tenantId){try{retrieval=await retrieveEvidence(String(body.tenantId),question,{domains:body.retrieval.domains,scopeId:body.retrieval.scopeId,municipalityIbge:body.retrieval.municipalityIbge,documentIds:body.retrieval.documentIds,topK:body.retrieval.topK,baseDate:body.retrieval.baseDate||body.baseDate,includePublic:body.retrieval.includePublic,knowledgeStatuses:body.retrieval.knowledgeStatuses,visibility:body.retrieval.visibility,knowledgeAt:body.retrieval.knowledgeAt});}catch(error:any){app.log.warn({error,traceId},'retrieval failed');retrieval={mode:'error',items:[],errors:[String(error?.message||error)]};}}
  const retrieved=(retrieval.items||[]).map((x:any)=>({id:x.id,title:x.title||`${x.domain||'Documento'} / ${x.documentId||x.id}`,locator:x.locator||`chunk:${x.id}`,text:x.text,metadata:{...(x.metadata||{}),retrieval:{mode:retrieval.mode,rrfScore:x.rrfScore,sources:x.retrievalSources}}}));
  const seen=new Set<string>();const evidence=[...retrieved,...contextEvidence].filter((x:any)=>{const id=String(x?.id||'');if(!id||seen.has(id))return false;seen.add(id);return true;}).slice(0,120);
  // When a configured provider exists, prefer grounded synthesis over dumping every confirmed rule.
  if(providerConfigured()&&evidence.length){
    try{let provider=await providerAnswer(assistant,question,evidence,traceId);if(provider){
      const confirmed=confirmedRules(rules);const decisive=['PERMITIDO','PROIBIDO','CONDICIONADO','CONFLITO'].includes(String(provider.decision_status||''));
      if(risk==='HIGH'&&decisive&&!confirmed.length)provider={...provider,status:'ABSTAINED',decision_status:'NAO_DETERMINADO',answer:'Há evidência textual recuperada, mas a conclusão de alto risco não possui regra determinística CONFIRMED aplicável. O sistema se abstém de declarar permitido, proibido ou viável.',uncertainty:'ALTA',professional_review:'OBRIGATORIA',limitations:[...(provider.limitations||[]),'high_risk_requires_confirmed_deterministic_rule'],missing_information:[...(provider.missing_information||[]),'Regra determinística CONFIRMED aplicável à conclusão de alto risco.']};
      else if(risk==='HIGH')provider={...provider,professional_review:'OBRIGATORIA'};
      const response={trace_id:traceId,assistant,risk_class:risk,...provider,retrieval:{mode:retrieval.mode,lexicalCount:retrieval.lexicalCount||0,vectorCount:retrieval.vectorCount||0,errors:retrieval.errors||[]}};void trace({traceId,tenantId:body.tenantId,assistant,model:process.env.AI_MODEL,status:provider.status,question,evidence,rules,metadata:{mode:provider.mode||'provider_abstained',latencyMs:Date.now()-started,evidenceIds:provider.evidence_ids,promptId:provider.prompt_id||null,promptVersion:provider.prompt_version||null,retrieval:response.retrieval}});return response;}}
    catch(error:any){app.log.warn({error,traceId},'provider adapter failed');}
  }
  const deterministic=deterministicAnswer(assistant,rules,evidence);
  if(deterministic){const response={status:'GROUNDED',trace_id:traceId,risk_class:risk,...deterministic,retrieval:{mode:retrieval.mode,lexicalCount:retrieval.lexicalCount||0,vectorCount:retrieval.vectorCount||0,errors:retrieval.errors||[]}};void trace({traceId,tenantId:body.tenantId,assistant,status:'GROUNDED',question,evidence,rules,metadata:{mode:deterministic.mode,latencyMs:Date.now()-started,retrieval:response.retrieval}});return response;}
  const response={status:'ABSTAINED',decision_status:'NAO_DETERMINADO',trace_id:traceId,assistant,risk_class:risk,answer:'Não há regra CONFIRMED suficiente nem evidência aterrada aprovada para responder. O gateway se abstém.',conditions:[],evidence_ids:[],uncertainty:'ALTA',missing_information:['Evidência verificável suficiente para sustentar a conclusão.'],professional_review:risk==='HIGH'?'OBRIGATORIA':'RECOMENDADA',limitations:['insufficient_grounding'],retrieval:{mode:retrieval.mode,lexicalCount:retrieval.lexicalCount||0,vectorCount:retrieval.vectorCount||0,errors:retrieval.errors||[]}};void trace({traceId,tenantId:body.tenantId,assistant,status:'ABSTAINED',question,evidence,rules,metadata:{reason:'insufficient_grounding_or_provider_failure',latencyMs:Date.now()-started,retrieval:response.retrieval}});return response;
});
app.post('/ai/v1/evaluate',async(req:any,reply:any)=>{if(!internal(req,reply))return{error:'forbidden'};const cases=Array.isArray(req.body?.cases)?req.body.cases:[];const results=cases.map((c:any)=>{const deterministic=deterministicAnswer(c.assistant||route(String(c.message||'')),Array.isArray(c.rules)?c.rules:[],Array.isArray(c.evidence)?c.evidence:[]);const actual=deterministic?'GROUNDED':'ABSTAINED';return{id:c.id||randomUUID(),expected:c.expectedStatus||null,actual,pass:!c.expectedStatus||c.expectedStatus===actual};});return{status:results.every((x:any)=>x.pass)?'PASS':'FAIL',total:results.length,passed:results.filter((x:any)=>x.pass).length,results};});

app.listen({host:'0.0.0.0',port:Number(process.env.PORT||3003)}).catch(error=>{console.error(error);process.exit(1);});
