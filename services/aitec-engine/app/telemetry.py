from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import threading
import time
import urllib.request
from collections import defaultdict

HTTP_BUCKETS=(0.005,0.01,0.025,0.05,0.1,0.25,0.5,1.0,1.5,2.5,5.0,10.0)
_lock=threading.Lock()
_active=0
_stats=defaultdict(lambda:{'count':0,'sum':0.0,'buckets':[0 for _ in HTTP_BUCKETS]})
_traceparent_re=re.compile(r'^00-([0-9a-fA-F]{32})-([0-9a-fA-F]{16})-[0-9a-fA-F]{2}$')


def _trace_ids(header:str|None):
    match=_traceparent_re.match(header or '')
    trace_id=(match.group(1).lower() if match else secrets.token_hex(16))
    return trace_id,secrets.token_hex(8)


def _record(method:str,status:int,duration:float):
    global _active
    status_class=f'{max(0,min(9,status//100))}xx'
    key=(method.upper()[:16],status_class)
    with _lock:
        _active=max(0,_active-1)
        item=_stats[key]
        item['count']+=1
        item['sum']+=max(0.0,duration)
        for index,limit in enumerate(HTTP_BUCKETS):
            if duration<=limit:item['buckets'][index]+=1


def _send_span(base:str,service:str,trace_id:str,span_id:str,start_ns:int,end_ns:int,method:str,path:str,status:int):
    payload={'resourceSpans':[{'resource':{'attributes':[{'key':'service.name','value':{'stringValue':service}},{'key':'service.version','value':{'stringValue':'19.0.0-rc.3'}}]},'scopeSpans':[{'scope':{'name':'lotediretor.native-http'},'spans':[{'traceId':trace_id,'spanId':span_id,'name':f'{method} {path}','kind':2,'startTimeUnixNano':str(start_ns),'endTimeUnixNano':str(end_ns),'attributes':[{'key':'http.request.method','value':{'stringValue':method}},{'key':'url.path','value':{'stringValue':path}},{'key':'http.response.status_code','value':{'intValue':str(status)}}],'status':{'code':2 if status>=500 else 1}}]}]}]}
    try:
        request=urllib.request.Request(base.rstrip('/')+'/v1/traces',data=json.dumps(payload).encode('utf-8'),headers={'content-type':'application/json'},method='POST')
        with urllib.request.urlopen(request,timeout=1.5) as response:
            response.read(1)
    except Exception:
        pass


async def http_telemetry(request,call_next):
    global _active
    method=str(request.method or 'HTTP').upper()
    path=str(request.url.path or '/')
    trace_id,span_id=_trace_ids(request.headers.get('traceparent'))
    start_perf=time.perf_counter()
    start_ns=time.time_ns()
    with _lock:_active+=1
    try:
        response=await call_next(request)
        status=int(response.status_code)
    except Exception:
        status=500
        duration=time.perf_counter()-start_perf
        _record(method,status,duration)
        base=os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT','').strip()
        if base:
            asyncio.create_task(asyncio.to_thread(_send_span,base,'aitec-engine',trace_id,span_id,start_ns,time.time_ns(),method,path,status))
        raise
    duration=time.perf_counter()-start_perf
    _record(method,status,duration)
    response.headers['traceparent']=f'00-{trace_id}-{span_id}-01'
    response.headers['x-trace-id']=trace_id
    base=os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT','').strip()
    if base:
        asyncio.create_task(asyncio.to_thread(_send_span,base,'aitec-engine',trace_id,span_id,start_ns,time.time_ns(),method,path,status))
    return response


def render_metrics(service:str):
    with _lock:
        active=_active
        snapshot={key:{'count':value['count'],'sum':value['sum'],'buckets':list(value['buckets'])} for key,value in _stats.items()}
    lines=[
        '# HELP lotediretor_http_requests_total Completed HTTP requests.',
        '# TYPE lotediretor_http_requests_total counter',
        '# HELP lotediretor_http_request_duration_seconds HTTP request duration histogram.',
        '# TYPE lotediretor_http_request_duration_seconds histogram',
        '# HELP lotediretor_http_requests_active HTTP requests currently in flight.',
        '# TYPE lotediretor_http_requests_active gauge',
        f'lotediretor_http_requests_active{{service="{service}"}} {active}',
    ]
    for (method,status_class),item in sorted(snapshot.items()):
        labels=f'service="{service}",method="{method}",status_class="{status_class}"'
        lines.append(f'lotediretor_http_requests_total{{{labels}}} {item["count"]}')
        for limit,count in zip(HTTP_BUCKETS,item['buckets']):
            lines.append(f'lotediretor_http_request_duration_seconds_bucket{{{labels},le="{limit}"}} {count}')
        lines.append(f'lotediretor_http_request_duration_seconds_bucket{{{labels},le="+Inf"}} {item["count"]}')
        lines.append(f'lotediretor_http_request_duration_seconds_sum{{{labels}}} {item["sum"]:.9f}')
        lines.append(f'lotediretor_http_request_duration_seconds_count{{{labels}}} {item["count"]}')
    return '\n'.join(lines)
