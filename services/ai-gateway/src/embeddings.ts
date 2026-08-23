export type EmbeddingResult={vector:number[];model:string;dimension:number};

function endpoint(){return String(process.env.AI_EMBEDDINGS_ENDPOINT||'').trim();}
function model(){return String(process.env.AI_EMBEDDINGS_MODEL||'').trim();}
function apiKey(){return String(process.env.AI_EMBEDDINGS_API_KEY||process.env.AI_API_KEY||'').trim();}

export function embeddingsConfigured(){return Boolean(endpoint()&&model()&&apiKey());}

export async function embedText(text:string):Promise<EmbeddingResult|null>{
  if(!embeddingsConfigured())return null;
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),Number(process.env.AI_EMBEDDINGS_TIMEOUT_MS||20000));
  try{
    const r=await fetch(endpoint(),{method:'POST',headers:{'content-type':'application/json','authorization':`Bearer ${apiKey()}`},signal:controller.signal,body:JSON.stringify({model:model(),input:text.slice(0,24000),encoding_format:'float'})});
    const raw:any=await r.json().catch(()=>({}));if(!r.ok)throw new Error(`embeddings_http_${r.status}`);
    const candidate=raw?.data?.[0]?.embedding??raw?.embedding??raw?.vector;
    if(!Array.isArray(candidate)||!candidate.length||candidate.some((x:any)=>!Number.isFinite(Number(x))))throw new Error('embeddings_invalid_vector');
    const vector=candidate.map((x:any)=>Number(x));const expected=Number(process.env.AI_EMBEDDINGS_DIMENSION||0);
    if(expected>0&&vector.length!==expected)throw new Error(`embeddings_dimension_${vector.length}_expected_${expected}`);
    return{vector,model:model(),dimension:vector.length};
  }finally{clearTimeout(timer);}
}
