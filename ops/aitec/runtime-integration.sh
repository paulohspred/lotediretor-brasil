#!/usr/bin/env bash
set -euo pipefail

OUT=/tmp/ld-aitec-v20-runtime.json

docker compose exec -T aitec-engine python - <<'PY' > "$OUT"
import json
import os
import urllib.request

base='http://127.0.0.1:8002'
token=os.environ['INTERNAL_API_TOKEN']

def call(path, payload=None):
    data=None if payload is None else json.dumps(payload).encode('utf-8')
    headers={'X-Internal-Token':token}
    if data is not None:headers['Content-Type']='application/json'
    req=urllib.request.Request(base+path,data=data,headers=headers,method='GET' if data is None else 'POST')
    with urllib.request.urlopen(req,timeout=20) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f'HTTP {response.status} for {path}')
        return json.load(response)

caps=call('/aitec/v20/capabilities')
ops={item['operation'] for item in caps['operations']}
required={'terrain.tin','building.solve','parking.basement','unit.room-graph','road.evaluate','environment.analyze','finance.calculate','optimization.pareto','export.ifc','ingest.ifc'}
missing=sorted(required-ops)
assert not missing, f'missing runtime operations:{missing}'
assert caps['classification']=='STUDY_PREPROJECT_NOT_EXECUTIVE'
assert caps['professional_review_required'] is True

result=call('/aitec/v20/execute/terrain.tin',{
  'kwargs':{'samples':[
    {'x':0,'y':0,'z':100},
    {'x':10,'y':0,'z':101},
    {'x':0,'y':10,'z':102},
    {'x':10,'y':10,'z':103}
  ]},
  'context':{'constraint_snapshot_id':'ci-aitec-snapshot-v20','seed':42}
})
assert result['status']=='EXECUTED', result
assert result['solver_version']=='aitec-terrain-v20.1', result
assert result['classification']=='STUDY_PREPROJECT_NOT_EXECUTIVE', result
assert result['context']['constraint_snapshot_id']=='ci-aitec-snapshot-v20', result
assert result['context']['seed']==42, result
assert result['result']['status']=='CALCULATED', result
assert result['result']['triangle_count'] >= 2, result

print(json.dumps({
  'status':'PASS',
  'capability_count':len(ops),
  'terrain_solver_version':result['solver_version'],
  'triangle_count':result['result']['triangle_count'],
  'classification':result['classification'],
  'constraint_snapshot_id':result['context']['constraint_snapshot_id'],
  'seed':result['context']['seed'],
},sort_keys=True))
PY

cat "$OUT"
echo "A.I TEC v20 advanced runtime API PASS"
