#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

root=Path(__file__).resolve().parents[2]
artifact=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else (root/'runtime-artifacts/cortex/latest').resolve()
status=sys.argv[2] if len(sys.argv)>2 else 'UNKNOWN'
profile=sys.argv[3] if len(sys.argv)>3 else os.environ.get('CORTEX_LOAD_PROFILE','ci')
artifact.mkdir(parents=True,exist_ok=True)


def run(*args:str):
    try:
        return subprocess.check_output(args,cwd=root,text=True,stderr=subprocess.DEVNULL,timeout=20).strip()
    except Exception:
        return None

commit=run('git','rev-parse','HEAD')
dirty=run('git','status','--porcelain')
images=[]
raw=run('docker','compose','images','--format','json')
if raw:
    try:
        parsed=json.loads(raw)
        if isinstance(parsed,list): images=parsed
        elif isinstance(parsed,dict): images=[parsed]
    except Exception:
        for line in raw.splitlines():
            try: images.append(json.loads(line))
            except Exception: pass

files=[]
manifest_path=artifact/'evidence-manifest.json'
for p in sorted(artifact.rglob('*')):
    if not p.is_file() or p==manifest_path: continue
    h=hashlib.sha256()
    try:
        with p.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
        files.append({'path':str(p.relative_to(artifact)),'bytes':p.stat().st_size,'sha256':h.hexdigest()})
    except OSError:
        pass

manifest={
    'schemaVersion':'lotediretor-cortex-evidence-v1',
    'generatedAtUtc':datetime.now(timezone.utc).isoformat(),
    'qualificationStatus':status,
    'loadProfile':profile,
    'git':{'commit':commit,'dirty':bool(dirty),'dirtyEntries':dirty.splitlines() if dirty else []},
    'composeImages':images,
    'artifacts':files,
    'invariants':[
        'tenant RLS remains enabled and non-owner runtime roles are used',
        'AI retrieval preserves tenant/public/temporal isolation',
        'Municipality Factory candidates require human review before confirmation',
        'privacy erasure is blocked by legal hold and protected evidence classes are retained',
        'productionHomologated remains false until external issue-13 gates are evidenced',
    ],
}
manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(manifest_path)
