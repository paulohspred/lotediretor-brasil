from __future__ import annotations

import hashlib
import json
import math
import re
from collections import deque
from datetime import date, datetime
from typing import Any

SOLAR_V20_VERSION = 'solar-scenario-v20.1'
CLASSIFICATION = 'PRELIMINARY_ENGINEERING_STUDY'
LOSS_COMPONENTS = ('temperature', 'soiling', 'shading', 'mismatch', 'wiring', 'inverter', 'availability')
SOURCE_KINDS = {'IMAGERY','DSM','DEM','BILL_OCR','TARIFF','BDGD','EQUIPMENT','CALIBRATION','OTHER'}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _missing(data: dict, fields: tuple[str, ...] | list[str]) -> list[str]:
    return [field for field in fields if data.get(field) in (None, '')]


def _parse_date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def validate_source_snapshot(source: dict) -> dict:
    required=('source_id','kind','captured_at','license_id','provenance_uri','checksum_sha256','crs')
    missing=_missing(source,required)
    if missing:
        return {'status':'REQUIRES_INPUT','missing':[f'source.{x}' for x in missing]}
    kind=str(source['kind']).upper()
    if kind not in SOURCE_KINDS:
        raise ValueError(f'unsupported source kind:{kind}')
    checksum=str(source['checksum_sha256']).lower()
    if not re.fullmatch(r'[0-9a-f]{64}',checksum):
        raise ValueError('source.checksum_sha256 must be a SHA-256 hex digest')
    try:
        datetime.fromisoformat(str(source['captured_at']).replace('Z','+00:00'))
    except Exception as exc:
        raise ValueError('source.captured_at must be ISO-8601') from exc
    normalized={
        'source_id':str(source['source_id']),
        'kind':kind,
        'captured_at':str(source['captured_at']),
        'license_id':str(source['license_id']),
        'provenance_uri':str(source['provenance_uri']),
        'checksum_sha256':checksum,
        'crs':str(source['crs']),
        'resolution_m':source.get('resolution_m'),
        'provider':source.get('provider'),
    }
    return {
        'status':'METADATA_COMPLETE',
        'source_snapshot_id':_fingerprint(normalized),
        'source':normalized,
        'content_verified':False,
        'limitations':['Metadados completos não equivalem a homologação da acurácia, licença ou conteúdo da fonte.'],
    }


def _normalize_dsm(samples: list[dict]) -> list[tuple[float,float,float]]:
    out=[];seen=set()
    for raw in samples or []:
        if raw.get('x') is None or raw.get('y') is None or raw.get('z') is None:
            raise ValueError('DSM samples require explicit x/y/z metric coordinates')
        row=(float(raw['x']),float(raw['y']),float(raw['z']))
        key=(round(row[0],6),round(row[1],6))
        if key in seen:raise ValueError(f'duplicate DSM XY sample:{key}')
        seen.add(key);out.append(row)
    return sorted(out)


def _cluster_points(points: list[tuple[float,float,float]], neighbor_m: float) -> list[list[tuple[float,float,float]]]:
    if neighbor_m<=0:raise ValueError('neighbor_m must be > 0')
    pending=set(range(len(points)));clusters=[]
    while pending:
        seed=min(pending);pending.remove(seed);queue=deque([seed]);cluster=[]
        while queue:
            i=queue.popleft();p=points[i];cluster.append(p)
            linked=[]
            for j in pending:
                q=points[j]
                if math.hypot(p[0]-q[0],p[1]-q[1])<=neighbor_m+1e-9:linked.append(j)
            for j in linked:pending.remove(j);queue.append(j)
        clusters.append(cluster)
    return clusters


def _bbox_polygon(points: list[tuple[float,float,float]], pad: float=0.0) -> dict:
    xs=[p[0] for p in points];ys=[p[1] for p in points]
    minx,maxx=min(xs)-pad,max(xs)+pad;miny,maxy=min(ys)-pad,max(ys)+pad
    return {'type':'Polygon','coordinates':[[[minx,miny],[maxx,miny],[maxx,maxy],[minx,maxy],[minx,miny]]]}


def segment_roof_surfaces(samples: list[dict], grid_step_m: float, elevation_band_m: float=0.5, min_samples: int=4) -> dict:
    if grid_step_m<=0 or elevation_band_m<=0 or min_samples<=0:raise ValueError('grid_step_m, elevation_band_m and min_samples must be > 0')
    pts=_normalize_dsm(samples)
    if len(pts)<min_samples:return {'status':'REQUIRES_INPUT','missing':['sufficient_dsm_samples'],'sample_count':len(pts)}
    bands:dict[int,list[tuple[float,float,float]]]={}
    for p in pts:bands.setdefault(round(p[2]/elevation_band_m),[]).append(p)
    surfaces=[];ordinal=1
    for band,band_pts in sorted(bands.items()):
        for cluster in _cluster_points(band_pts,grid_step_m*1.6):
            if len(cluster)<min_samples:continue
            zs=[p[2] for p in cluster]
            surfaces.append({
                'id':f'ROOF-{ordinal:04d}','sample_count':len(cluster),'mean_elevation_m':round(sum(zs)/len(zs),3),
                'min_elevation_m':round(min(zs),3),'max_elevation_m':round(max(zs),3),
                'geometry':_bbox_polygon(cluster,grid_step_m/2),'elevation_band':band,
            });ordinal+=1
    return {
        'status':'PRELIMINARY_DSM_SEGMENTATION' if surfaces else 'NO_SURFACE_CANDIDATE',
        'solver_version':SOLAR_V20_VERSION,'surfaces':surfaces,
        'limitations':['Segmentação por conectividade e banda de elevação em DSM explícito; não substitui classificação fotogramétrica/LiDAR homologada.'],
    }


def detect_dsm_obstacles(samples: list[dict], roof_reference_elevation_m: float, threshold_m: float, grid_step_m: float, min_samples: int=1) -> dict:
    if threshold_m<=0 or grid_step_m<=0 or min_samples<=0:raise ValueError('threshold_m, grid_step_m and min_samples must be > 0')
    pts=_normalize_dsm(samples)
    elevated=[p for p in pts if p[2]-float(roof_reference_elevation_m)>=threshold_m]
    obstacles=[]
    for ordinal,cluster in enumerate([c for c in _cluster_points(elevated,grid_step_m*1.6) if len(c)>=min_samples],start=1):
        heights=[p[2]-float(roof_reference_elevation_m) for p in cluster]
        obstacles.append({'id':f'OBS-{ordinal:04d}','sample_count':len(cluster),'max_height_m':round(max(heights),3),'mean_height_m':round(sum(heights)/len(heights),3),'geometry':_bbox_polygon(cluster,grid_step_m/2)})
    return {'status':'PRELIMINARY_DSM_OBSTACLES','solver_version':SOLAR_V20_VERSION,'obstacles':obstacles,'threshold_m':threshold_m,'limitations':['Detecção baseada somente em anomalia de altura relativa ao plano de referência fornecido.']}


def project_shadows(obstacles: list[dict], solar_azimuth_deg: float, solar_elevation_deg: float) -> dict:
    if not 0 < solar_elevation_deg <= 90:
        return {'status':'NO_DIRECT_SUN','solver_version':SOLAR_V20_VERSION,'shadows':[]}
    az=math.radians(float(solar_azimuth_deg)%360);elev=math.radians(float(solar_elevation_deg));out=[]
    for i,item in enumerate(obstacles or [],start=1):
        missing=_missing(item,('x_m','y_m','width_m','depth_m','height_m'))
        if missing:return {'status':'REQUIRES_INPUT','missing':[f'obstacles[{i-1}].{x}' for x in missing]}
        x=float(item['x_m']);y=float(item['y_m']);w=float(item['width_m']);d=float(item['depth_m']);h=float(item['height_m'])
        if min(w,d,h)<0:raise ValueError('obstacle dimensions/heights must be non-negative')
        length=h/max(math.tan(elev),1e-12);dx=-math.sin(az)*length;dy=-math.cos(az)*length
        base=[(x,y),(x+w,y),(x+w,y+d),(x,y+d)]
        shifted=[(px+dx,py+dy) for px,py in base]
        hull=base+shifted
        # Deterministic convex hull without external geometry dependency.
        points=sorted(set(hull))
        def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
        lower=[]
        for p in points:
            while len(lower)>=2 and cross(lower[-2],lower[-1],p)<=0:lower.pop()
            lower.append(p)
        upper=[]
        for p in reversed(points):
            while len(upper)>=2 and cross(upper[-2],upper[-1],p)<=0:upper.pop()
            upper.append(p)
        ring=(lower[:-1]+upper[:-1]);ring.append(ring[0])
        out.append({'id':str(item.get('id') or f'OBS-{i:04d}'),'shadow_length_m':round(length,3),'geometry':{'type':'Polygon','coordinates':[[[round(px,4),round(py,4)] for px,py in ring]]}})
    return {'status':'CALCULATED_GEOMETRIC_SHADOW','solver_version':SOLAR_V20_VERSION,'solar_azimuth_deg':float(solar_azimuth_deg)%360,'solar_elevation_deg':float(solar_elevation_deg),'shadows':out,'limitations':['Projeção geométrica plana; não inclui relevo, penumbra, reflexão ou modelo atmosférico.']}


def energy_from_irradiance(dc_kwp: float, monthly_poa_kwh_m2: list[float], loss_fractions: dict) -> dict:
    if dc_kwp<=0:raise ValueError('dc_kwp must be > 0')
    if len(monthly_poa_kwh_m2)!=12 or any(float(v)<0 for v in monthly_poa_kwh_m2):raise ValueError('monthly_poa_kwh_m2 must contain 12 non-negative values')
    missing=[name for name in LOSS_COMPONENTS if loss_fractions.get(name) is None]
    if missing:return {'status':'REQUIRES_INPUT','missing':[f'loss_fractions.{name}' for name in missing]}
    losses={name:float(loss_fractions[name]) for name in LOSS_COMPONENTS}
    if any(v<0 or v>=1 for v in losses.values()):raise ValueError('loss fractions must be in [0,1)')
    performance=1.0
    for value in losses.values():performance*=1-value
    ideal=[dc_kwp*float(v) for v in monthly_poa_kwh_m2];net=[v*performance for v in ideal]
    return {'status':'CALCULATED_FROM_EXPLICIT_IRRADIANCE_AND_LOSSES','solver_version':SOLAR_V20_VERSION,'dc_kwp':dc_kwp,'performance_factor':round(performance,6),'loss_fractions':losses,'monthly_ideal_kwh':[round(v,2) for v in ideal],'monthly_net_kwh':[round(v,2) for v in net],'annual_net_kwh':round(sum(net),2),'limitations':['Irradiância POA deve vir de fonte/calibração externa identificada; o motor não inventa recurso solar.']}


def simulate_battery(load_kwh: list[float], pv_kwh: list[float], capacity_kwh: float, power_kw: float, interval_hours: float, roundtrip_efficiency: float, min_soc_fraction: float, initial_soc_fraction: float) -> dict:
    if len(load_kwh)!=len(pv_kwh) or not load_kwh:raise ValueError('load_kwh and pv_kwh must have the same non-zero length')
    if any(float(v)<0 for v in load_kwh+pv_kwh):raise ValueError('energy series values must be non-negative')
    if capacity_kwh<=0 or power_kw<=0 or interval_hours<=0:raise ValueError('battery capacity/power/interval must be > 0')
    if not 0<roundtrip_efficiency<=1:raise ValueError('roundtrip_efficiency must be in (0,1]')
    if not 0<=min_soc_fraction<1 or not min_soc_fraction<=initial_soc_fraction<=1:raise ValueError('invalid SOC fractions')
    charge_eff=math.sqrt(roundtrip_efficiency);discharge_eff=charge_eff
    min_soc=capacity_kwh*min_soc_fraction;soc=capacity_kwh*initial_soc_fraction;max_step=power_kw*interval_hours
    grid_import=[];grid_export=[];soc_series=[];charged=0.0;discharged=0.0
    for load,pv in zip(map(float,load_kwh),map(float,pv_kwh)):
        surplus=pv-load
        if surplus>=0:
            ac_charge=min(surplus,max_step,max(0.0,(capacity_kwh-soc)/charge_eff));soc+=ac_charge*charge_eff;charged+=ac_charge;grid_export.append(surplus-ac_charge);grid_import.append(0.0)
        else:
            deficit=-surplus;available_ac=max(0.0,(soc-min_soc)*discharge_eff);ac_discharge=min(deficit,max_step,available_ac);soc-=ac_discharge/discharge_eff;discharged+=ac_discharge;grid_import.append(deficit-ac_discharge);grid_export.append(0.0)
        soc=max(min_soc,min(capacity_kwh,soc));soc_series.append(soc)
    equivalent_cycles=(discharged/capacity_kwh) if capacity_kwh else None
    return {'status':'CALCULATED_BATTERY_DISPATCH','solver_version':SOLAR_V20_VERSION,'grid_import_kwh':[round(v,4) for v in grid_import],'grid_export_kwh':[round(v,4) for v in grid_export],'soc_kwh':[round(v,4) for v in soc_series],'charged_ac_kwh':round(charged,4),'discharged_ac_kwh':round(discharged,4),'equivalent_full_cycles':round(equivalent_cycles,4),'assumptions':{'capacity_kwh':capacity_kwh,'power_kw':power_kw,'interval_hours':interval_hours,'roundtrip_efficiency':roundtrip_efficiency,'min_soc_fraction':min_soc_fraction,'initial_soc_fraction':initial_soc_fraction}}


def apply_tariff_snapshot(energy_balance: dict, tariff_snapshot: dict, base_date: str) -> dict:
    required=('snapshot_id','effective_from','effective_to','grid_purchase_rate_brl_per_kwh','injection_credit_rate_brl_per_kwh','minimum_bill_brl','law_reference','components','source_snapshot_id')
    missing=_missing(tariff_snapshot,required)
    if missing:return {'status':'REQUIRES_INPUT','missing':[f'tariff_snapshot.{x}' for x in missing]}
    when=_parse_date(base_date);start=_parse_date(tariff_snapshot['effective_from']);end=_parse_date(tariff_snapshot['effective_to'])
    if not start<=when<=end:return {'status':'OUTSIDE_TARIFF_EFFECTIVE_PERIOD','base_date':when.isoformat(),'effective_from':start.isoformat(),'effective_to':end.isoformat()}
    components=tariff_snapshot['components']
    for key in ('TE','TUSD','SCEE','LAW_14300_RULESET'):
        if key not in components:return {'status':'REQUIRES_INPUT','missing':[f'tariff_snapshot.components.{key}']}
    purchases=energy_balance.get('grid_purchase_monthly_kwh');injected=energy_balance.get('injected_monthly_kwh')
    if not isinstance(purchases,list) or not isinstance(injected,list) or len(purchases)!=12 or len(injected)!=12:return {'status':'REQUIRES_INPUT','missing':['energy_balance.grid_purchase_monthly_kwh','energy_balance.injected_monthly_kwh']}
    purchase_rate=float(tariff_snapshot['grid_purchase_rate_brl_per_kwh']);credit_rate=float(tariff_snapshot['injection_credit_rate_brl_per_kwh']);minimum=float(tariff_snapshot['minimum_bill_brl'])
    if min(purchase_rate,credit_rate,minimum)<0:raise ValueError('tariff rates and minimum bill must be non-negative')
    monthly=[]
    for month,(buy,inj) in enumerate(zip(map(float,purchases),map(float,injected)),start=1):
        energy_charge=buy*purchase_rate;credit=inj*credit_rate;bill=max(minimum,energy_charge-credit)
        monthly.append({'month':month,'grid_purchase_kwh':round(buy,2),'injected_kwh':round(inj,2),'energy_charge_brl':round(energy_charge,2),'injection_credit_brl':round(credit,2),'bill_brl':round(bill,2)})
    return {'status':'CALCULATED_FROM_VERSIONED_TARIFF_SNAPSHOT','solver_version':SOLAR_V20_VERSION,'snapshot_id':tariff_snapshot['snapshot_id'],'base_date':when.isoformat(),'law_reference':tariff_snapshot['law_reference'],'components':components,'monthly':monthly,'annual_bill_brl':round(sum(x['bill_brl'] for x in monthly),2),'limitations':['O motor aplica apenas taxas/regras explicitamente fornecidas no snapshot; interpretação regulatória continua sujeita a validação jurídica/tarifária.']}


def connection_precheck(inputs: dict) -> dict:
    required=('requested_ac_kw','requested_export_kw','available_transformer_kw','feeder_hosting_capacity_kw','max_export_kw','connection_voltage_v','source_snapshot_id')
    missing=_missing(inputs,required)
    if missing:return {'status':'REQUIRES_INPUT','missing':[f'connection.{x}' for x in missing]}
    requested=float(inputs['requested_ac_kw']);export=float(inputs['requested_export_kw']);transformer=float(inputs['available_transformer_kw']);feeder=float(inputs['feeder_hosting_capacity_kw']);max_export=float(inputs['max_export_kw'])
    if min(requested,export,transformer,feeder,max_export)<0:raise ValueError('connection capacities must be non-negative')
    checks=[
        {'code':'TRANSFORMER_CAPACITY','status':'PASS' if requested<=transformer+1e-9 else 'FAIL','observed_kw':requested,'limit_kw':transformer},
        {'code':'FEEDER_HOSTING_CAPACITY','status':'PASS' if requested<=feeder+1e-9 else 'FAIL','observed_kw':requested,'limit_kw':feeder},
        {'code':'EXPORT_LIMIT','status':'PASS' if export<=max_export+1e-9 else 'FAIL','observed_kw':export,'limit_kw':max_export},
    ]
    return {'status':'PRECHECK_PASS' if all(c['status']=='PASS' for c in checks) else 'PRECHECK_FAIL','solver_version':SOLAR_V20_VERSION,'checks':checks,'connection_voltage_v':inputs['connection_voltage_v'],'source_snapshot_id':inputs['source_snapshot_id'],'limitations':['Pré-check não substitui parecer de acesso, estudo de proteção, fluxo de potência ou aprovação da distribuidora.']}


def ground_mount_layout(inputs: dict) -> dict:
    required=('site_width_m','site_depth_m','module_width_m','module_length_m','row_pitch_m','modules_per_table','tracker_mode','source_snapshot_id')
    missing=_missing(inputs,required)
    if missing:return {'status':'REQUIRES_INPUT','missing':[f'ground_mount.{x}' for x in missing]}
    width=float(inputs['site_width_m']);depth=float(inputs['site_depth_m']);mw=float(inputs['module_width_m']);ml=float(inputs['module_length_m']);pitch=float(inputs['row_pitch_m']);per_table=int(inputs['modules_per_table']);mode=str(inputs['tracker_mode']).upper()
    if min(width,depth,mw,ml,pitch,per_table)<=0:raise ValueError('ground-mount dimensions/counts must be positive')
    if mode not in ('FIXED','SINGLE_AXIS'):raise ValueError('tracker_mode must be FIXED or SINGLE_AXIS')
    if mode=='SINGLE_AXIS' and inputs.get('tracker_rotation_limit_deg') is None:return {'status':'REQUIRES_INPUT','missing':['ground_mount.tracker_rotation_limit_deg']}
    table_width=mw*per_table;tables_per_row=int(width//table_width);rows=int(depth//pitch);count=tables_per_row*rows*per_table
    module_area=mw*ml;gcr=(rows*ml/depth) if depth>0 else 0
    return {'status':'PRELIMINARY_GROUND_MOUNT_LAYOUT','solver_version':SOLAR_V20_VERSION,'tracker_mode':mode,'row_count':rows,'tables_per_row':tables_per_row,'panel_count':count,'module_area_m2':round(module_area,3),'ground_coverage_ratio':round(gcr,4),'row_pitch_m':pitch,'tracker_rotation_limit_deg':inputs.get('tracker_rotation_limit_deg'),'source_snapshot_id':inputs['source_snapshot_id'],'limitations':['Layout cartesiano preliminar; relevo, fundações, drenagem, sombreamento entre fileiras e envelope mecânico do tracker exigem engenharia específica.']}


def safety_conditioning(inputs: dict) -> dict:
    required=('roof_load_capacity_kg_m2','system_dead_load_kg_m2','required_fire_setback_m','provided_fire_setback_m','structural_review_status','fire_review_status')
    missing=_missing(inputs,required)
    if missing:return {'status':'REQUIRES_INPUT','missing':[f'safety.{x}' for x in missing]}
    capacity=float(inputs['roof_load_capacity_kg_m2']);dead=float(inputs['system_dead_load_kg_m2']);required=float(inputs['required_fire_setback_m']);provided=float(inputs['provided_fire_setback_m'])
    checks=[
        {'code':'STRUCTURAL_LOAD','status':'PASS' if dead<=capacity+1e-9 else 'FAIL','observed':dead,'limit':capacity,'unit':'kg/m2'},
        {'code':'FIRE_SETBACK','status':'PASS' if provided+1e-9>=required else 'FAIL','observed':provided,'limit':required,'unit':'m'},
    ]
    reviews={'structural':str(inputs['structural_review_status']).upper(),'fire':str(inputs['fire_review_status']).upper()}
    if any(c['status']=='FAIL' for c in checks):status='CONDITIONING_FAIL'
    elif any(value!='REVIEWED' for value in reviews.values()):status='REQUIRES_PROFESSIONAL_REVIEW'
    else:status='CONDITIONING_PASS_REVIEW_RECORDED'
    return {'status':status,'solver_version':SOLAR_V20_VERSION,'checks':checks,'reviews':reviews,'limitations':['Registro de review não transfere responsabilidade técnica ao software e não converte estudo em projeto executivo.']}


def calibration_compare(predicted_kwh: list[float], observed_kwh: list[float], reference_id: str) -> dict:
    if not reference_id:return {'status':'REQUIRES_INPUT','missing':['reference_id']}
    if len(predicted_kwh)!=len(observed_kwh) or not predicted_kwh:raise ValueError('predicted and observed series must have the same non-zero length')
    p=list(map(float,predicted_kwh));o=list(map(float,observed_kwh))
    if any(v<0 for v in p+o):raise ValueError('calibration energy values must be non-negative')
    errors=[a-b for a,b in zip(p,o)];rmse=math.sqrt(sum(e*e for e in errors)/len(errors));den=sum(o)
    bias=(sum(p)-sum(o))/den if den>0 else None
    ape=[abs(a-b)/b for a,b in zip(p,o) if b>0];mape=sum(ape)/len(ape) if ape else None
    return {'status':'CALIBRATION_COMPARISON','solver_version':SOLAR_V20_VERSION,'reference_id':reference_id,'sample_count':len(p),'rmse_kwh':round(rmse,4),'normalized_bias':None if bias is None else round(bias,6),'mape':None if mape is None else round(mape,6),'limitations':['Métricas descrevem comparação com a referência fornecida; não provam independência, qualidade metrológica ou generalização do modelo.']}


def parse_bill_ocr_text(text: str, ocr_source: dict) -> dict:
    if not text.strip():return {'status':'REQUIRES_INPUT','missing':['ocr_text']}
    source=validate_source_snapshot(ocr_source)
    if source.get('status')=='REQUIRES_INPUT':return {'status':'REQUIRES_INPUT','missing':source['missing']}
    normalized=text.replace('\xa0',' ')
    kwh=[]
    for match in re.finditer(r'(?i)(\d{1,3}(?:[\.\s]\d{3})*(?:[,\.]\d+)?)\s*kwh',normalized):
        raw=match.group(1).replace(' ','')
        if ',' in raw:raw=raw.replace('.','').replace(',','.')
        kwh.append(float(raw))
    currency=[]
    for match in re.finditer(r'R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})|\d+(?:[,\.]\d{2})?)',normalized,re.I):
        raw=match.group(1)
        if ',' in raw:raw=raw.replace('.','').replace(',','.')
        currency.append(float(raw))
    return {'status':'REQUIRES_REVIEW','solver_version':SOLAR_V20_VERSION,'source_snapshot_id':source['source_snapshot_id'],'consumption_candidates_kwh':kwh,'currency_candidates_brl':currency,'confidence':'UNASSESSED','limitations':['Parser recebe texto de OCR; não executa OCR e nunca promove automaticamente candidatos a valores faturados confirmados.']}


def equipment_snapshot(equipment: dict) -> dict:
    required=('equipment_type','manufacturer','model','datasheet_uri','datasheet_sha256','source_uri','captured_at')
    missing=_missing(equipment,required)
    if missing:return {'status':'REQUIRES_INPUT','missing':[f'equipment.{x}' for x in missing]}
    checksum=str(equipment['datasheet_sha256']).lower()
    if not re.fullmatch(r'[0-9a-f]{64}',checksum):raise ValueError('equipment.datasheet_sha256 must be SHA-256 hex')
    normalized={k:equipment[k] for k in sorted(equipment)}
    normalized['datasheet_sha256']=checksum
    return {'status':'CATALOG_SNAPSHOT_RECORDED','solver_version':SOLAR_V20_VERSION,'equipment_snapshot_id':_fingerprint(normalized),'equipment':normalized,'commercial_availability_verified':False,'limitations':['Snapshot registra dados fornecidos; preço, disponibilidade e homologação comercial exigem fonte externa atualizada.']}


def build_scene_3d(surfaces: list[dict], obstacles: list[dict], panels: list[dict], source_snapshot_ids: list[str]) -> dict:
    if not source_snapshot_ids:return {'status':'REQUIRES_INPUT','missing':['source_snapshot_ids']}
    objects=[]
    for kind,items in [('SURFACE',surfaces),('OBSTACLE',obstacles),('PANEL',panels)]:
        for index,item in enumerate(items or [],start=1):
            objects.append({'id':str(item.get('id') or f'{kind}-{index:04d}'),'kind':kind,'geometry':item.get('geometry'),'height_m':item.get('height_m'),'properties':{k:v for k,v in item.items() if k not in ('geometry','id')}})
    return {'status':'SCENE_MODEL_READY','solver_version':SOLAR_V20_VERSION,'coordinate_convention':'local_metric_xy_z_up','source_snapshot_ids':list(source_snapshot_ids),'objects':objects,'renderer_contract':{'threejs':True,'cesium':True,'format':'JSON_SCENE_V20'},'limitations':['Contrato de cena não substitui renderer WebGL nem valida precisão 3D da fonte.']}


def build_scenario_report(scenario_id: str, base_date: str, sources: list[dict], assumptions: dict, outputs: dict, confidence: dict, uncertainty: dict) -> dict:
    if not scenario_id:return {'status':'REQUIRES_INPUT','missing':['scenario_id']}
    _parse_date(base_date)
    source_results=[validate_source_snapshot(source) for source in sources]
    missing=[]
    for result in source_results:
        if result.get('status')=='REQUIRES_INPUT':missing.extend(result['missing'])
    if missing:return {'status':'REQUIRES_INPUT','missing':sorted(set(missing))}
    if not confidence:return {'status':'REQUIRES_INPUT','missing':['confidence']}
    if not uncertainty:return {'status':'REQUIRES_INPUT','missing':['uncertainty']}
    body={'scenario_id':scenario_id,'base_date':base_date,'solver_version':SOLAR_V20_VERSION,'classification':CLASSIFICATION,'sources':[r['source']|{'source_snapshot_id':r['source_snapshot_id']} for r in source_results],'assumptions':assumptions,'outputs':outputs,'confidence':confidence,'uncertainty':uncertainty,'external_gates':['licensed/current source verification','utility connection approval','structural/fire professional review','independent calibration/real-system validation']}
    return {'status':'REPORT_READY','report_fingerprint':_fingerprint(body),**body}
