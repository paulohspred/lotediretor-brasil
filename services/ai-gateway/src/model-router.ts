export type ModelUsage={promptTokens:number|null;completionTokens:number|null;totalTokens:number|null;costUsd:number|null};
export type ModelAttempt={providerId:string;model:string;status:'SUCCESS'|'FAILED'|'SKIPPED_CIRCUIT_OPEN';latencyMs:number;reason?:string;httpStatus?:number};
export type ModelRouterResult={content:any;raw:any;providerId:string;model:string;usage:ModelUsage;attempts:ModelAttempt[]};

type ProviderConfig={id:string;endpoint:string;apiKey:string;model:string;timeoutMs:number;inputCostPer1M:number|null;outputCostPer1M:number|null};
type CircuitState={failures:number;openedUntil:number};
const circuits=new Map<string,CircuitState>();

function positiveNumber(value:string|undefined,fallback:number){const n=Number(value);return Number.isFinite(n)&&n>0?n:fallback;}
function optionalNonNegative(value:string|undefined){if(value===undefined||value==='')return null;const n=Number(value);return Number.isFinite(n)&&n>=0?n:null;}
function normalizeEndpoint(value:string){return value.replace(/\/$/,'');}

function provider(prefix:'PRIMARY'|'FALLBACK'):ProviderConfig|null{
  const fallback=prefix==='FALLBACK';
  const endpoint=fallback?(process.env.AI_FALLBACK_CHAT_ENDPOINT||process.env.AI_FALLBACK_BASE_URL||''):(process.env.AI_CHAT_ENDPOINT||process.env.AI_BASE_URL||'');
  const apiKey=fallback?(process.env.AI_FALLBACK_API_KEY||''):(process.env.AI_API_KEY||'');
  const model=fallback?(process.env.AI_FALLBACK_MODEL||''):(process.env.AI_MODEL||'');
  if(!endpoint||!apiKey||!model)return null;
  const timeoutMs=positiveNumber(fallback?process.env.AI_FALLBACK_TIMEOUT_MS:process.env.AI_TIMEOUT_MS,30000);
  const inputCostPer1M=optionalNonNegative(fallback?process.env.AI_FALLBACK_INPUT_COST_PER_1M_USD:process.env.AI_INPUT_COST_PER_1M_USD);
  const outputCostPer1M=optionalNonNegative(fallback?process.env.AI_FALLBACK_OUTPUT_COST_PER_1M_USD:process.env.AI_OUTPUT_COST_PER_1M_USD);
  return{id:fallback?'fallback':'primary',endpoint:normalizeEndpoint(endpoint),apiKey,model,timeoutMs,inputCostPer1M,outputCostPer1M};
}

export function configuredProviders(){return [provider('PRIMARY'),provider('FALLBACK')].filter((x):x is ProviderConfig=>Boolean(x));}
export function modelProvidersConfigured(){return configuredProviders().length>0;}

function threshold(){return Math.max(1,Math.floor(positiveNumber(process.env.AI_CIRCUIT_FAILURE_THRESHOLD,3)));}
function resetMs(){return Math.max(1000,positiveNumber(process.env.AI_CIRCUIT_RESET_MS,60000));}
function circuitOpen(id:string,now=Date.now()){const c=circuits.get(id);if(!c)return false;if(c.openedUntil&&c.openedUntil<=now){circuits.set(id,{failures:0,openedUntil:0});return false;}return c.openedUntil>now;}
function recordSuccess(id:string){circuits.set(id,{failures:0,openedUntil:0});}
function recordFailure(id:string){const current=circuits.get(id)||{failures:0,openedUntil:0};const failures=current.failures+1;circuits.set(id,{failures,openedUntil:failures>=threshold()?Date.now()+resetMs():0});}

function usageFrom(raw:any,p:ProviderConfig):ModelUsage{
  const u=raw?.usage||{};const promptTokens=Number.isFinite(Number(u.prompt_tokens))?Number(u.prompt_tokens):null;const completionTokens=Number.isFinite(Number(u.completion_tokens))?Number(u.completion_tokens):null;const totalTokens=Number.isFinite(Number(u.total_tokens))?Number(u.total_tokens):(promptTokens!==null&&completionTokens!==null?promptTokens+completionTokens:null);
  let costUsd:number|null=null;
  if(promptTokens!==null&&completionTokens!==null&&p.inputCostPer1M!==null&&p.outputCostPer1M!==null)costUsd=(promptTokens/1_000_000)*p.inputCostPer1M+(completionTokens/1_000_000)*p.outputCostPer1M;
  return{promptTokens,completionTokens,totalTokens,costUsd};
}

export function modelRouterStatus(){
  return configuredProviders().map(p=>{const c=circuits.get(p.id)||{failures:0,openedUntil:0};return{id:p.id,model:p.model,configured:true,timeoutMs:p.timeoutMs,circuit:{failures:c.failures,open:circuitOpen(p.id),openedUntil:c.openedUntil||null},costRatesConfigured:p.inputCostPer1M!==null&&p.outputCostPer1M!==null};});
}

export async function routeChat(messages:any[],options:{temperature?:number;responseFormat?:any;traceId?:string}={}):Promise<ModelRouterResult|null>{
  const providers=configuredProviders();if(!providers.length)return null;const attempts:ModelAttempt[]=[];
  for(const p of providers){
    if(circuitOpen(p.id)){attempts.push({providerId:p.id,model:p.model,status:'SKIPPED_CIRCUIT_OPEN',latencyMs:0,reason:'circuit_open'});continue;}
    const started=Date.now();const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),p.timeoutMs);
    try{
      const body:any={model:p.model,messages,temperature:options.temperature??0};if(options.responseFormat)body.response_format=options.responseFormat;
      const r=await fetch(p.endpoint,{method:'POST',headers:{'content-type':'application/json','authorization':`Bearer ${p.apiKey}`,'x-lotediretor-trace-id':options.traceId||''},signal:controller.signal,body:JSON.stringify(body)});
      const raw:any=await r.json().catch(()=>({}));
      if(!r.ok){recordFailure(p.id);attempts.push({providerId:p.id,model:p.model,status:'FAILED',latencyMs:Date.now()-started,httpStatus:r.status,reason:`provider_http_${r.status}`});continue;}
      const content=raw?.choices?.[0]?.message?.content??raw?.output_text??raw?.content;if(content===undefined||content===null){recordFailure(p.id);attempts.push({providerId:p.id,model:p.model,status:'FAILED',latencyMs:Date.now()-started,reason:'provider_missing_content'});continue;}
      recordSuccess(p.id);attempts.push({providerId:p.id,model:p.model,status:'SUCCESS',latencyMs:Date.now()-started});return{content,raw,providerId:p.id,model:p.model,usage:usageFrom(raw,p),attempts};
    }catch(error:any){recordFailure(p.id);const reason=error?.name==='AbortError'?'provider_timeout':String(error?.message||error||'provider_error');attempts.push({providerId:p.id,model:p.model,status:'FAILED',latencyMs:Date.now()-started,reason});}
    finally{clearTimeout(timer);}
  }
  const error:any=new Error('all_model_providers_failed_or_unavailable');error.attempts=attempts;throw error;
}
