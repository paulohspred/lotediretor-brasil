#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,sys,urllib.request
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--file',default='data/ai-evals/golden-v19.json');ap.add_argument('--url',default=os.getenv('AI_GATEWAY_URL','http://localhost:3003'));args=ap.parse_args()
    token=os.getenv('INTERNAL_API_TOKEN','').strip()
    if not token:raise SystemExit('INTERNAL_API_TOKEN is required')
    payload=json.loads(Path(args.file).read_text())
    req=urllib.request.Request(args.url.rstrip('/')+'/ai/v1/evaluate',data=json.dumps({'cases':payload['cases']}).encode(),headers={'content-type':'application/json','x-internal-token':token},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=30) as r:out=json.loads(r.read())
    except Exception as exc:raise SystemExit(f'ai golden eval request failed: {exc}')
    print(json.dumps(out,ensure_ascii=False,indent=2))
    if out.get('status')!='PASS':return 1
    return 0
if __name__=='__main__':sys.exit(main())
