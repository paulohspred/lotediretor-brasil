#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,sys
import requests
import xml.etree.ElementTree as ET

def local(tag:str)->str:return tag.rsplit('}',1)[-1]

def discover(url:str,pattern:str|None=None,timeout:int=60):
    r=requests.get(url,params={'service':'WFS','request':'GetCapabilities','version':'2.0.0'},headers={'user-agent':'LoteDiretor/19-beta'},timeout=timeout);r.raise_for_status()
    root=ET.fromstring(r.content);features=[];rx=re.compile(pattern,re.I) if pattern else None
    for el in root.iter():
        if local(el.tag)!='FeatureType':continue
        fields={}
        for child in list(el):
            name=local(child.tag)
            if name in {'Name','Title','Abstract','DefaultCRS','DefaultSRS'} and child.text:fields[name]=child.text.strip()
        if not fields.get('Name'):continue
        hay=' '.join(fields.values())
        if rx and not rx.search(hay):continue
        features.append({'typeName':fields.get('Name'),'title':fields.get('Title'),'abstract':fields.get('Abstract'),'defaultCrs':fields.get('DefaultCRS') or fields.get('DefaultSRS')})
    return{'url':r.url,'status':r.status_code,'featureTypes':features,'count':len(features),'warning':'Discovery is not activation. Pin the exact typeName, license and dataset contract before ingestion.'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--url',required=True);ap.add_argument('--pattern');ap.add_argument('--timeout',type=int,default=60);args=ap.parse_args()
    try:out=discover(args.url,args.pattern,args.timeout)
    except Exception as exc:print(json.dumps({'status':'ERROR','error':str(exc)},ensure_ascii=False),file=sys.stderr);return 1
    print(json.dumps(out,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':sys.exit(main())
