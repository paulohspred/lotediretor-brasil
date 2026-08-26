from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import urllib.error

os.environ.setdefault('PLATFORM_DATABASE_URL','postgresql://unused')
os.environ.setdefault('INTERNAL_API_TOKEN','unit-test-token')
os.environ.setdefault('AITEC_JOB_MAX_RESPONSE_BYTES','4096')

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('aitec_worker',ROOT/'workers'/'aitec'/'main.py')
worker=importlib.util.module_from_spec(spec)
assert spec and spec.loader
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

print('v20 A.I TEC worker engine trust-boundary tests OK')
