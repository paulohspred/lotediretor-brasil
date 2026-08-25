from __future__ import annotations

import hashlib
import json
from typing import Any

from shapely.geometry import mapping, shape

OPTIMIZATION_VERSION='aitec-optimization-v20.1'


def explain_pareto(scenarios:list[dict],objectives:dict[str,str])->dict[str,Any]:
    if not objectives:raise ValueError('at least one Pareto objective is required')
    directions={metric:str(direction).upper() for metric,direction in objectives.items()}
    for metric,direction in directions.items():
        if direction not in ('MAX','MIN'):raise ValueError(f'invalid objective direction:{metric}:{direction}')
    eligible=[];excluded=[]
    for scenario in scenarios:
        sid=str(scenario.get('id') or '')
        if not sid:raise ValueError('every scenario requires id')
        if scenario.get('hard_invalid'):
            excluded.append({'id':sid,'reason':'hard_invalid'});continue
        metrics=scenario.get('metrics') or {};values={};missing=[]
        for metric in directions:
            raw=metrics.get(metric)
            if raw is None or isinstance(raw,bool):missing.append(metric);continue
            try:values[metric]=float(raw)
            except Exception:missing.append(metric)
        if missing:excluded.append({'id':sid,'reason':'objective_missing_or_non_numeric','metrics':missing});continue
        eligible.append({'id':sid,'metrics':metrics,'values':values})
    ranges={metric:(min(item['values'][metric] for item in eligible),max(item['values'][metric] for item in eligible)) for metric in directions} if eligible else {}
    def dominates(left,right):
        weak=True;strict=False
        for metric,direction in directions.items():
            a=left['values'][metric];b=right['values'][metric]
            if direction=='MAX':
                if a<b:weak=False;break
                if a>b:strict=True
            else:
                if a>b:weak=False;break
                if a<b:strict=True
        return weak and strict
    results=[]
    for item in eligible:
        dominators=[]
        for other in eligible:
            if other['id']!=item['id'] and dominates(other,item):dominators.append(other['id'])
        normalized={}
        for metric,direction in directions.items():
            lo,hi=ranges[metric];value=item['values'][metric]
            norm=1.0 if hi==lo else (value-lo)/(hi-lo)
            if direction=='MIN':norm=1.0-norm
            normalized[metric]=round(norm,6)
        score=sum(normalized.values())/len(normalized)
        results.append({'id':item['id'],'frontier':not dominators,'dominated_by':sorted(dominators),'metrics':item['metrics'],'normalized_objectives':normalized,'balanced_score':round(score,6)})
    frontier=sorted([item for item in results if item['frontier']],key=lambda item:(-item['balanced_score'],item['id']))
    dominated=sorted([item for item in results if not item['frontier']],key=lambda item:item['id'])
    return {'version':OPTIMIZATION_VERSION,'objectives':directions,'frontier':frontier,'dominated':dominated,'excluded':excluded,'policy':'Pareto frontier uses only hard-valid scenarios with every objective explicitly numeric; balanced_score is explanatory and never changes dominance.'}


def visual_geometry_diff(before:dict,after:dict,key_property:str='id')->dict[str,Any]:
    if before.get('type')!='FeatureCollection' or after.get('type')!='FeatureCollection':raise ValueError('visual diff requires FeatureCollection inputs')
    def index(fc):
        out={}
        for pos,feature in enumerate(fc.get('features') or []):
            props=feature.get('properties') or {};key=props.get(key_property)
            if key is None:raise ValueError(f'feature missing key_property:{key_property}')
            key=str(key)
            if key in out:raise ValueError(f'duplicate feature key:{key}')
            out[key]=(feature,shape(feature['geometry']))
        return out
    left=index(before);right=index(after);features=[];summary=[]
    for key in sorted(set(left)|set(right)):
        if key not in left:
            geom=right[key][1];change='ADDED';changed_area=float(geom.area)
        elif key not in right:
            geom=left[key][1];change='REMOVED';changed_area=float(geom.area)
        else:
            a=left[key][1];b=right[key][1]
            if a.equals_exact(b,1e-9):
                summary.append({'id':key,'change':'UNCHANGED','changed_area_m2':0.0});continue
            geom=a.symmetric_difference(b);change='CHANGED';changed_area=float(geom.area)
        if geom is not None and not geom.is_empty:features.append({'type':'Feature','properties':{key_property:key,'change':change,'changed_area_m2':round(changed_area,6)},'geometry':mapping(geom)})
        summary.append({'id':key,'change':change,'changed_area_m2':round(changed_area,6)})
    result={'version':OPTIMIZATION_VERSION,'key_property':key_property,'summary':summary,'diff':{'type':'FeatureCollection','features':features}}
    canonical=json.dumps(result,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8');result['fingerprint']=hashlib.sha256(canonical).hexdigest();return result
