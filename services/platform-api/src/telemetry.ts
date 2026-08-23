import {PLATFORM_VERSION} from './version';
import {randomBytes} from 'crypto';
type TraceState={traceId:string;spanId:string;startNs:bigint;name:string};
function hex(n:number){return randomBytes(n).toString('hex')}
export function beginHttpTrace(req:any):TraceState{
  const tp=String(req.headers?.traceparent||'');const m=/^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$/i.exec(tp);
  const state={traceId:m?.[1]?.toLowerCase()||hex(16),spanId:hex(8),startNs:BigInt(Date.now())*1000000n,name:`${req.method||'HTTP'} ${req.url||'/'}`};
  req.ldTrace=state;req.traceId=state.traceId;return state;
}
export function traceparent(s:TraceState){return `00-${s.traceId}-${s.spanId}-01`}
export function finishHttpTrace(service:string,req:any,reply:any){
  const s=req.ldTrace as TraceState|undefined;const base=(process.env.OTEL_EXPORTER_OTLP_ENDPOINT||'').replace(/\/$/,'');if(!s||!base)return;
  const end=BigInt(Date.now())*1000000n;const status=Number(reply.statusCode||200);
  const payload={resourceSpans:[{resource:{attributes:[{key:'service.name',value:{stringValue:service}},{key:'service.version',value:{stringValue:PLATFORM_VERSION}}]},scopeSpans:[{scope:{name:'lotediretor.native-http'},spans:[{traceId:s.traceId,spanId:s.spanId,name:s.name,kind:2,startTimeUnixNano:String(s.startNs),endTimeUnixNano:String(end),attributes:[{key:'http.request.method',value:{stringValue:String(req.method||'')}},{key:'url.path',value:{stringValue:String(req.url||'').split('?')[0]}},{key:'http.response.status_code',value:{intValue:String(status)}}],status:{code:status>=500?2:1}}]}]}]};
  const ac=new AbortController();const timer=setTimeout(()=>ac.abort(),1500);
  void fetch(`${base}/v1/traces`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload),signal:ac.signal}).catch(()=>{}).finally(()=>clearTimeout(timer));
}
