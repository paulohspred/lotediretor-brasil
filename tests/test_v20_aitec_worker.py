from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import urllib.error

os.environ.setdefault('PLATFORM_DATABASE_URL','postgresql://unused')
os.environ.setdefault('INTERNAL_API_TOKEN','unit-test-token')
os.environ.setdefault('AITEC_JOB_MAX_RESPONSE_BYTES','4096')

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('aitec_worker',ROOT/'workers'/'aitec'/'main.py')
assert spec and spec.loader
worker=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=worker
spec.loader.exec_module(worker)

JOB={
    'id':'job-1',
    'tenant_id':'tenant-a',
    'project_id':'project-a',
    'constraint_snapshot_id':'constraint-a',
    'operation':'terrain.tin',
    'args':[],
    'kwargs':{'samples':[{'x':0,'y':0,'z':0},{'x':1,'y':0,'z':0},{'x':0,'y':1,'z':1}]},
    'context':{'tenant_id':'tenant-a','project_id':'project-a','constraint_snapshot_id':'constraint-a','seed':42},
    'attempts':1,
}

class FakeResponse:
    def __init__(self,payload,status=200):
        self.payload=payload if isinstance(payload,bytes) else json.dumps(payload).encode()
        self.status=status
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n=-1): return self.payload if n<0 else self.payload[:n]

def response(**overrides):
    base={
        'status':'EXECUTED','operation':'terrain.tin','solver_version':'aitec-terrain-v20.1',
        'classification':'STUDY_PREPROJECT_NOT_EXECUTIVE','professional_review_required':True,
        'context':dict(JOB['context']),'result':{'status':'CALCULATED','triangle_count':1},
    }
    base.update(overrides)
    return base

def expect_failure(expected,retryable,fn):
    try: fn()
    except worker.EngineFailure as exc:
        assert expected in str(exc),(expected,str(exc))
        assert exc.retryable is retryable,(expected,exc.retryable)
    else: raise AssertionError(f'expected EngineFailure containing {expected}')

original=worker.urllib.request.urlopen
try:
    worker.urllib.request.urlopen=lambda request,timeout: FakeResponse(response())
    good=worker.execute_engine(dict(JOB))
    assert good['solver_version']=='aitec-terrain-v20.1'
    assert good['context']['seed']==42

    bad=response(context={**JOB['context'],'tenant_id':'tenant-b'})
    worker.urllib.request.urlopen=lambda request,timeout: FakeResponse(bad)
    expect_failure('aitec_engine_context_mismatch',False,lambda:worker.execute_engine(dict(JOB)))

    bad=response(context={**JOB['context'],'project_id':'project-b'})
    worker.urllib.request.urlopen=lambda request,timeout: FakeResponse(bad)
    expect_failure('aitec_engine_context_mismatch',False,lambda:worker.execute_engine(dict(JOB)))

    bad=response(context={**JOB['context'],'constraint_snapshot_id':'constraint-b'})
    worker.urllib.request.urlopen=lambda request,timeout: FakeResponse(bad)
    expect_failure('aitec_engine_constraint_context_mismatch',False,lambda:worker.execute_engine(dict(JOB)))

    worker.urllib.request.urlopen=lambda request,timeout: FakeResponse(response(status='READY'))
    expect_failure('aitec_engine_contract_mismatch',False,lambda:worker.execute_engine(dict(JOB)))

    worker.urllib.request.urlopen=lambda request,timeout: FakeResponse(b'not-json')
    expect_failure('aitec_engine_invalid_json',False,lambda:worker.execute_engine(dict(JOB)))

    worker.urllib.request.urlopen=lambda request,timeout: FakeResponse(b'x'*(worker.MAX_RESPONSE_BYTES+1))
    expect_failure('aitec_engine_response_too_large',False,lambda:worker.execute_engine(dict(JOB)))

    def unreachable(request,timeout): raise urllib.error.URLError('synthetic-unreachable')
    worker.urllib.request.urlopen=unreachable
    expect_failure('aitec_engine_unreachable',True,lambda:worker.execute_engine(dict(JOB)))
finally:
    worker.urllib.request.urlopen=original

# Queue telemetry must remain low-cardinality. Tenant/project/job/operation identifiers
# are deliberately excluded from labels; they remain in logs/persisted evidence instead.
assert tuple(worker.JOB_STATE._labelnames)==('status',)
assert tuple(worker.OLDEST_JOB_AGE._labelnames)==('status',)
assert tuple(worker.JOB_EXECUTIONS._labelnames)==('result',)
assert tuple(worker.STALE_RECLAIMS._labelnames)==('result',)
for metric in (worker.JOB_STATE,worker.OLDEST_JOB_AGE,worker.JOB_EXECUTIONS,worker.STALE_RECLAIMS):
    labels=set(metric._labelnames)
    assert not labels.intersection({'tenant','tenant_id','project','project_id','job','job_id','operation'}),labels

class FakeRows:
    def __init__(self,rows): self.rows=rows
    def fetchall(self): return self.rows

class FakeConn:
    def execute(self,sql,*args,**kwargs):
        assert 'from aitec.job' in sql.lower()
        return FakeRows([('QUEUED',3,12.5),('RUNNING',1,2.0),('FAILED',2,90.0)])

worker._last_metrics_refresh=0.0
worker.refresh_queue_metrics(FakeConn(),force=True)
assert worker.JOB_STATE.labels(status='QUEUED')._value.get()==3
assert worker.JOB_STATE.labels(status='RUNNING')._value.get()==1
assert worker.JOB_STATE.labels(status='COMPLETED')._value.get()==0
assert worker.JOB_STATE.labels(status='CANCELLED')._value.get()==0
assert worker.OLDEST_JOB_AGE.labels(status='FAILED')._value.get()==90.0
assert worker.LAST_DB_SUCCESS._value.get()>0

print('v20 A.I TEC worker trust-boundary + low-cardinality telemetry tests OK')
