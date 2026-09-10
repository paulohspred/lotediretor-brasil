'use client';
import {useEffect,useState} from 'react';
import type {ApiError,JobSnapshot} from '@lotediretor/api-contracts';

function errorMessage(x:any,status:number){const e=x as Partial<ApiError>|null;return e?.message||e?.code||`HTTP ${status}`;}
class HttpResponseError extends Error{constructor(public readonly status:number,message:string){super(message);this.name='HttpResponseError';}}
export async function getJson<T=any>(url:string):Promise<T>{const r=await fetch(url,{credentials:'include',cache:'no-store'});const x=await r.json().catch(()=>null);if(!r.ok)throw new HttpResponseError(r.status,errorMessage(x,r.status));return x;}
export function useApi<T>(url:string){
  const [data,setData]=useState<T|null>(null);const [error,setError]=useState('');const [loading,setLoading]=useState(true);
  const load=async()=>{setLoading(true);setError('');try{setData(await getJson<T>(url))}catch(e:any){setError(e?.message||String(e))}finally{setLoading(false)}};
  useEffect(()=>{void load()},[url]);return {data,error,loading,reload:load,setData};
}
export async function postJson<T=any>(url:string,body:any,options?:{idempotent?:boolean;retries?:number}):Promise<T>{
  const key=options?.idempotent?(globalThis.crypto?.randomUUID?.()||`${Date.now()}-${Math.random()}`):null;const retries=options?.retries??(options?.idempotent?1:0);
  for(let attempt=0;;attempt++){
    const headers:Record<string,string>={'content-type':'application/json'};if(key)headers['Idempotency-Key']=key;
    try{
      const r=await fetch(url,{method:'POST',headers,credentials:'include',body:JSON.stringify(body)});const x=await r.json().catch(()=>null);
      if(!r.ok){
        if(attempt<retries&&[502,503,504].includes(r.status)){await new Promise(res=>setTimeout(res,400*(attempt+1)));continue;}
        throw new HttpResponseError(r.status,errorMessage(x,r.status));
      }
      return x;
    }catch(e){
      // HTTP responses are deterministic application outcomes unless explicitly
      // classified above as transient gateway failures. Retry only transport errors.
      if(e instanceof HttpResponseError)throw e;
      if(attempt<retries){await new Promise(res=>setTimeout(res,400*(attempt+1)));continue;}
      throw e;
    }
  }
}
export async function uploadFile<T=any>(file:File):Promise<T>{const form=new FormData();form.append('file',file);const r=await fetch('/api/v1/files/upload',{method:'POST',credentials:'include',body:form});const x=await r.json().catch(()=>null);if(!r.ok)throw new HttpResponseError(r.status,errorMessage(x,r.status));return x;}
export async function pollJson<T=any>(url:string,predicate:(value:T)=>boolean,timeoutMs=30000,intervalMs=1200):Promise<T>{const started=Date.now();while(true){const value=await getJson<T>(url);if(predicate(value))return value;if(Date.now()-started>timeoutMs)throw new Error('Tempo de espera excedido');await new Promise(r=>setTimeout(r,intervalMs));}}
export function waitForJob(jobId:string,timeoutMs=60000):Promise<JobSnapshot>{
  return new Promise((resolve,reject)=>{const es=new EventSource(`/api/v1/events/jobs/${encodeURIComponent(jobId)}`,{withCredentials:true});const timer=setTimeout(()=>{es.close();reject(new Error('Tempo de espera do job excedido'));},timeoutMs);const finish=(fn:()=>void)=>{clearTimeout(timer);es.close();fn();};
    es.addEventListener('job',(event:any)=>{try{const data=JSON.parse(event.data) as JobSnapshot;if(['COMPLETED','FAILED','CANCELLED','REJECTED'].includes(String(data.status).toUpperCase()))finish(()=>data.status==='COMPLETED'?resolve(data):reject(new Error(`Job ${data.status}`)));}catch{}});
    es.onerror=()=>finish(()=>reject(new Error('Fluxo de progresso do job foi interrompido')));
  });
}
export function State({loading,error,empty}:{loading:boolean;error:string;empty?:string}){if(loading)return <div className="notice neutral">Carregando dados do backend…</div>;if(error)return <div className="notice error">{error==='unauthorized'?'Sessão necessária. Entre novamente pelo login.':error}</div>;if(empty)return <div className="notice neutral">{empty}</div>;return null;}
