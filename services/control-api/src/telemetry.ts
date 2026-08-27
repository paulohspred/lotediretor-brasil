import {CONTROL_VERSION} from './version';
import {randomBytes} from 'crypto';

type TraceState={traceId:string;spanId:string;startNs:bigint;name:string};
type HttpMetric={count:number;sumSeconds:number;buckets:number[]};

const HTTP_BUCKETS=[0.005,0.01,0.025,0.05,0.1,0.25,0.5,1,1.5,2.5,5,10];
const HTTP_METRICS=new Map<string,HttpMetric>();
let ACTIVE_REQUESTS=0;

function hex(n:number){return randomBytes(n).toString('hex')}
function metricKey(method:string,statusClass:string){return `${method}|${statusClass}`}
function escapeLabel(value:string){return value.replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/\n/g,'\\n')}

function recordHttp(methodRaw:any,status:number,durationSeconds:number){
  const method=String(methodRaw||'UNKNOWN').toUpperCase().slice(0,16);
  const statusClass=Number.isFinite(status)?`${Math.max(0,Math.min(9,Math.floor(status/100)))}xx`:'unknown';
  const key=metricKey(method,statusClass);
  const metric=HTTP_METRICS.get(key)||{count:0,sumSeconds:0,buckets:HTTP_BUCKETS.map(()=>0)};
  metric.count+=1;
  metric.sumSeconds+=Math.max(0,durationSeconds);
  HTTP_BUCKETS.forEach((le,index)=>{if(durationSeconds<=le)metric.buckets[index]+=1});
  HTTP_METRICS.set(key,metric);
}

export function beginHttpTrace(req:any):TraceState{
  const tp=String(req.headers?.traceparent||'');const m=/^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$/i.exec(tp);
  const state={traceId:m?.[1]?.toLowerCase()||hex(16),spanId:hex(8),startNs:process.hrtime.bigint(),name:`${req.method||'HTTP'} ${req.url||'/'}`};
  ACTIVE_REQUESTS+=1;
  req.ldTrace=state;req.traceId=state.traceId;return state;
}
export function traceparent(s:TraceState){return `00-${s.traceId}-${s.spanId}-01`}

export function finishHttpTrace(service:string,req:any,reply:any){
  const s=req.ldTrace as TraceState|undefined;
  if(!s)return;
  const elapsedNs=process.hrtime.bigint()-s.startNs;
  const durationSeconds=Number(elapsedNs)/1e9;
  const status=Number(reply.statusCode||200);
  ACTIVE_REQUESTS=Math.max(0,ACTIVE_REQUESTS-1);
  recordHttp(req.method,status,durationSeconds);

  const base=(process.env.OTEL_EXPORTER_OTLP_ENDPOINT||'').replace(/\/$/,'');
  if(!base)return;
  const endUnixNs=BigInt(Date.now())*1000000n;
  const startUnixNs=endUnixNs-elapsedNs;
  const payload={resourceSpans:[{resource:{attributes:[{key:'service.name',value:{stringValue:service}},{key:'service.version',value:{stringValue:CONTROL_VERSION}}]},scopeSpans:[{scope:{name:'lotediretor.native-http'},spans:[{traceId:s.traceId,spanId:s.spanId,name:s.name,kind:2,startTimeUnixNano:String(startUnixNs),endTimeUnixNano:String(endUnixNs),attributes:[{key:'http.request.method',value:{stringValue:String(req.method||'')}},{key:'url.path',value:{stringValue:String(req.url||'').split('?')[0]}},{key:'http.response.status_code',value:{intValue:String(status)}}],status:{code:status>=500?2:1}}]}]}]};
  const ac=new AbortController();const timer=setTimeout(()=>ac.abort(),1500);
  void fetch(`${base}/v1/traces`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload),signal:ac.signal}).catch(()=>{}).finally(()=>clearTimeout(timer));
}

export function renderHttpMetrics(service:string){
  const s=escapeLabel(service);
  const lines=[
    '# HELP lotediretor_http_requests_total Completed HTTP requests.',
    '# TYPE lotediretor_http_requests_total counter',
    '# HELP lotediretor_http_request_duration_seconds HTTP request duration histogram.',
    '# TYPE lotediretor_http_request_duration_seconds histogram',
    '# HELP lotediretor_http_requests_active HTTP requests currently in flight.',
    '# TYPE lotediretor_http_requests_active gauge',
    `lotediretor_http_requests_active{service="${s}"} ${ACTIVE_REQUESTS}`,
  ];
  for(const [key,metric] of [...HTTP_METRICS.entries()].sort(([a],[b])=>a.localeCompare(b))){
    const [method,statusClass]=key.split('|').map(escapeLabel);
    const labels=`service="${s}",method="${method}",status_class="${statusClass}"`;
    lines.push(`lotediretor_http_requests_total{${labels}} ${metric.count}`);
    HTTP_BUCKETS.forEach((le,index)=>lines.push(`lotediretor_http_request_duration_seconds_bucket{${labels},le="${le}"} ${metric.buckets[index]}`));
    lines.push(`lotediretor_http_request_duration_seconds_bucket{${labels},le="+Inf"} ${metric.count}`);
    lines.push(`lotediretor_http_request_duration_seconds_sum{${labels}} ${metric.sumSeconds.toFixed(9)}`);
    lines.push(`lotediretor_http_request_duration_seconds_count{${labels}} ${metric.count}`);
  }
  return lines.join('\n');
}
