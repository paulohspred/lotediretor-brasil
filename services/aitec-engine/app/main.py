from __future__ import annotations
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel, Field
from typing import Any
from uuid import uuid4
import os
from shapely.geometry import shape, mapping
from shapely.ops import transform, unary_union
from pyproj import CRS, Transformer
from .domain import parking_area,massing_capacity,rank_scenarios,validate_hard_constraints,generate_site_solutions,pareto_frontier,generate_access_road_layout,allocate_unit_mix,estimate_cut_fill_from_samples,solve_building_stack

app=FastAPI(title='LoteDiretor A.I TEC Engine',version='19.0.0-rc.3')

def internal_token(x_internal_token:str|None=Header(default=None)):
    expected=os.getenv('INTERNAL_API_TOKEN','')
    if not expected or x_internal_token!=expected: raise HTTPException(403,'forbidden')

class Job(BaseModel):
    project_id:str
    constraint_snapshot_id:str
    objectives:list[str]=Field(default_factory=list)
    program:dict[str,Any]=Field(default_factory=dict)

class EnvelopeInput(BaseModel):
    polygon:dict[str,Any]
    setback_m:float=Field(ge=0,le=1000)

class DirectionalSetback(BaseModel):
    kind:str
    line:dict[str,Any]
    setback_m:float=Field(ge=0,le=1000)

class DirectionalEnvelopeInput(BaseModel):
    polygon:dict[str,Any]
    edges:list[DirectionalSetback]
    edge_match_tolerance_m:float=Field(default=1.0,gt=0,le=20)

class HardConstraint(BaseModel):
    code:str
    metric:str
    operator:str
    value:float|None=None
    min_value:float|None=None
    max_value:float|None=None
    tolerance:float=Field(default=1e-9,ge=0)

class ConstraintValidationInput(BaseModel):
    metrics:dict[str,Any]
    constraints:list[HardConstraint]=Field(default_factory=list)

class ParkingInput(BaseModel):
    required_spaces:int=Field(ge=0,le=100000)
    stall_width_m:float=Field(default=2.5,gt=0)
    stall_length_m:float=Field(default=5.0,gt=0)
    circulation_factor:float=Field(default=1.65,ge=1.0,le=5.0)

class UnitProgramInput(BaseModel):unit_types:list[dict[str,Any]]
class MassingInput(BaseModel):
    parcel_area_m2:float=Field(gt=0);buildable_area_m2:float=Field(gt=0);ca_max:float=Field(ge=0);height_max_m:float|None=Field(default=None,gt=0);floor_height_m:float=Field(default=3.0,gt=0);efficiency:float=Field(default=0.78,gt=0,le=1)
class ParetoInput(BaseModel):
    scenarios:list[dict[str,Any]];weights:dict[str,float]

class SiteSolverInput(BaseModel):
    polygon:dict[str,Any]
    setback_m:float=Field(default=3.0,ge=0,le=1000)
    ca_max:float=Field(gt=0,le=50)
    to_max:float=Field(gt=0,le=1)
    tp_min:float=Field(default=0,ge=0,le=1)
    height_max_m:float=Field(gt=0,le=1000)
    floor_height_m:float=Field(default=3.0,gt=0,le=20)
    efficiency:float=Field(default=.78,gt=0,le=1)
    avg_unit_area_m2:float=Field(default=65,gt=5,le=5000)
    min_buildings:int=Field(default=1,ge=1,le=20)
    max_buildings:int=Field(default=4,ge=1,le=20)
    min_spacing_m:float=Field(default=8,ge=0,le=200)
    spaces_per_unit:float=Field(default=1.0,ge=0,le=10)
    required_spaces:int|None=Field(default=None,ge=0,le=100000)
    stall_width_m:float=Field(default=2.5,gt=1.5,le=5.0)
    stall_length_m:float=Field(default=5.0,gt=3.0,le=10.0)
    aisle_width_m:float=Field(default=6.0,gt=2.0,le=20.0)
    access_point:dict[str,Any]|None=None
    access_required:bool=False
    road_width_m:float=Field(default=6.0,gt=2.0,le=30.0)
    unit_mix:list[dict[str,Any]]=Field(default_factory=list)
    min_total_units:int|None=Field(default=None,ge=0,le=100000)
    terrain_samples:list[dict[str,Any]]=Field(default_factory=list)
    core_area_m2:float=Field(default=40.0,gt=4,le=5000)
    circulation_width_m:float=Field(default=1.8,gt=.5,le=20)
    locked_footprints:list[dict[str,Any]]=Field(default_factory=list)
    count:int=Field(default=30,ge=1,le=200)
    seed:int=Field(default=1,ge=0,le=2147483647)

class UnitMixAllocationInput(BaseModel):
    net_area_m2:float=Field(ge=0)
    unit_types:list[dict[str,Any]]
    min_total_units:int|None=Field(default=None,ge=0)

class AccessRoadInput(BaseModel):
    polygon:dict[str,Any]
    building_footprints:list[dict[str,Any]]=Field(default_factory=list)
    parking_aisles:list[dict[str,Any]]=Field(default_factory=list)
    access_point:dict[str,Any]
    road_width_m:float=Field(default=6.0,gt=2.0,le=30.0)

class CutFillInput(BaseModel):
    footprints:list[dict[str,Any]]
    terrain_samples:list[dict[str,Any]]

class BuildingStackInput(BaseModel):
    footprints:list[dict[str,Any]]
    floors:int=Field(ge=1,le=200)
    core_area_m2:float=Field(default=40.0,gt=4,le=5000)
    circulation_width_m:float=Field(default=1.8,gt=.5,le=20)


@app.get('/aitec/health')
def health():return {'ok':True,'service':'aitec-engine','version':'19.0.0-rc.3'}

@app.post('/aitec/v1/jobs')
def create_job(x:Job, _:None=Depends(internal_token)):
    return {'job_id':str(uuid4()),'status':'accepted_for_orchestration','solver_status':'requires_validated_geometry_and_constraints','message':'O job foi aceito, mas nenhum cenário é classificado como válido sem validator de constraints duras.','input_snapshot':x.model_dump()}

def utm_for_lon_lat(lon:float,lat:float)->CRS:
    zone=int((lon+180)//6)+1;epsg=(32600 if lat>=0 else 32700)+zone;return CRS.from_epsg(epsg)

@app.post('/aitec/v1/envelope')
def envelope(x:EnvelopeInput, _:None=Depends(internal_token)):
    try:geom=shape(x.polygon)
    except Exception as exc:raise HTTPException(400,f'GeoJSON inválido: {exc}')
    if geom.geom_type not in ('Polygon','MultiPolygon') or geom.is_empty or not geom.is_valid:raise HTTPException(400,'É necessário Polygon/MultiPolygon GeoJSON válido.')
    c=geom.centroid;crs=utm_for_lon_lat(c.x,c.y);fwd=Transformer.from_crs(4326,crs,always_xy=True).transform;inv=Transformer.from_crs(crs,4326,always_xy=True).transform;metric=transform(fwd,geom);inner=metric.buffer(-x.setback_m,join_style=2)
    if inner.is_empty:return {'status':'INVALID','reason':'setback_eliminates_buildable_area','setback_m':x.setback_m,'parcel_area_m2':metric.area}
    out=transform(inv,inner)
    return {'status':'CALCULATED','method':'uniform_metric_buffer','projection':crs.to_string(),'setback_m':x.setback_m,'parcel_area_m2':round(metric.area,2),'buildable_area_m2':round(inner.area,2),'geometry':mapping(out),'limitations':['Recuo uniforme não identifica frente/lateral/fundos. Essas classificações exigem dado explícito.']}

@app.post('/aitec/v1/envelope-directional')
def envelope_directional(x:DirectionalEnvelopeInput, _:None=Depends(internal_token)):
    try:geom=shape(x.polygon)
    except Exception as exc:raise HTTPException(400,f'GeoJSON inválido: {exc}')
    if geom.geom_type not in ('Polygon','MultiPolygon') or geom.is_empty or not geom.is_valid:raise HTTPException(400,'É necessário Polygon/MultiPolygon GeoJSON válido.')
    if not x.edges:raise HTTPException(400,'edges explícitas são obrigatórias para envelope direcional')
    c=geom.centroid;crs=utm_for_lon_lat(c.x,c.y);fwd=Transformer.from_crs(4326,crs,always_xy=True).transform;inv=Transformer.from_crs(crs,4326,always_xy=True).transform;metric=transform(fwd,geom)
    cuts=[];applied=[]
    for edge in x.edges:
        try:line=shape(edge.line)
        except Exception as exc:raise HTTPException(400,f'Linha de recuo inválida ({edge.kind}): {exc}')
        if line.geom_type not in ('LineString','MultiLineString') or line.is_empty or not line.is_valid:raise HTTPException(400,f'Edge {edge.kind} precisa ser LineString/MultiLineString válido')
        mline=transform(fwd,line);distance=mline.distance(metric.boundary)
        if distance>x.edge_match_tolerance_m:raise HTTPException(409,f'edge_not_on_parcel_boundary:{edge.kind}:distance_m={distance:.3f}')
        if edge.setback_m>0:cuts.append(mline.buffer(edge.setback_m,cap_style=2,join_style=2))
        applied.append({'kind':edge.kind,'setback_m':edge.setback_m,'boundary_distance_m':round(distance,3)})
    inner=metric.difference(unary_union(cuts) if cuts else metric.buffer(0)).intersection(metric) if cuts else metric
    if inner.is_empty:return {'status':'INVALID','reason':'directional_setbacks_eliminate_buildable_area','parcel_area_m2':round(metric.area,2),'applied':applied}
    out=transform(inv,inner)
    return {'status':'CALCULATED','method':'explicit_boundary_strip_difference','projection':crs.to_string(),'parcel_area_m2':round(metric.area,2),'buildable_area_m2':round(inner.area,2),'geometry':mapping(out),'applied':applied,'limitations':['Classificação frente/lateral/fundos é aceita somente quando fornecida explicitamente; o motor não a inventa.','A operação é envelope urbanístico preliminar e não substitui levantamento/projeto legal.']}


@app.post('/aitec/v1/validate-constraints')
def validate_constraints(x:ConstraintValidationInput, _:None=Depends(internal_token)):
    return validate_hard_constraints(x.metrics,[item.model_dump() for item in x.constraints])

@app.post('/aitec/v1/parking')
def parking(x:ParkingInput, _:None=Depends(internal_token)):
    try:r=parking_area(x.required_spaces,x.stall_width_m,x.stall_length_m,x.circulation_factor)
    except ValueError as exc:raise HTTPException(400,str(exc))
    return {'status':'PRELIMINARY','required_spaces':x.required_spaces,'stall_area_m2':round(r['stall_area_m2'],2),'gross_area_per_space_m2':round(r['gross_area_per_space_m2'],2),'estimated_total_area_m2':round(r['estimated_total_area_m2'],2),'assumptions':x.model_dump(exclude={'required_spaces'}),'limitations':['Estimativa de área; não substitui layout geométrico, acessibilidade, rampas, circulação ou legislação local.']}

@app.post('/aitec/v1/unit-program')
def unit_program(x:UnitProgramInput, _:None=Depends(internal_token)):
    total_units=0;private_area=0.0;normalized=[]
    for item in x.unit_types:
        name=str(item.get('name') or item.get('type') or 'Unidade');qty=int(item.get('quantity') or 0);area=float(item.get('target_area_m2') or 0)
        if qty<0 or area<0:raise HTTPException(400,'quantity/target_area_m2 não podem ser negativos')
        total_units+=qty;private_area+=qty*area;normalized.append({'name':name,'quantity':qty,'target_area_m2':area,'total_private_area_m2':round(qty*area,2)})
    return {'status':'CALCULATED','total_units':total_units,'total_private_area_m2':round(private_area,2),'unit_types':normalized}

@app.post('/aitec/v1/massing')
def massing(x:MassingInput, _:None=Depends(internal_token)):
    try:r=massing_capacity(x.parcel_area_m2,x.buildable_area_m2,x.ca_max,x.height_max_m,x.floor_height_m,x.efficiency)
    except ValueError as exc:raise HTTPException(400,str(exc))
    return {'status':'PRELIMINARY_VALIDATED_MATH',**{k:(round(v,2) if isinstance(v,float) else v) for k,v in r.items()},'assumptions':x.model_dump(),'limitations':['Não gera arquitetura executiva. Não considera núcleos, fachadas, insolação, circulação vertical, estrutura, incêndio ou código local além dos limites fornecidos.']}


@app.post('/aitec/v1/unit-mix')
def unit_mix_allocate(x:UnitMixAllocationInput, _:None=Depends(internal_token)):
    try:return allocate_unit_mix(x.net_area_m2,x.unit_types,x.min_total_units)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/aitec/v1/access-road')
def access_road(x:AccessRoadInput, _:None=Depends(internal_token)):
    try:
        parcel=shape(x.polygon);buildings=[shape(g) for g in x.building_footprints];aisles=[shape(g) for g in x.parking_aisles];access=shape(x.access_point)
    except Exception as exc:raise HTTPException(400,f'GeoJSON inválido: {exc}')
    if parcel.geom_type not in ('Polygon','MultiPolygon') or not parcel.is_valid:raise HTTPException(400,'polygon inválido')
    c=parcel.centroid;crs=utm_for_lon_lat(c.x,c.y);fwd=Transformer.from_crs(4326,crs,always_xy=True).transform;inv=Transformer.from_crs(crs,4326,always_xy=True).transform
    out=generate_access_road_layout(transform(fwd,parcel),[transform(fwd,g) for g in buildings],[transform(fwd,g) for g in aisles],transform(fwd,access),x.road_width_m)
    serial={k:v for k,v in out.items() if k not in ('road','centerline')}
    if out.get('road') is not None:serial['geometry']=mapping(transform(inv,out['road']))
    if out.get('centerline') is not None:serial['centerline']=mapping(transform(inv,out['centerline']))
    serial['projection']=crs.to_string();return serial

@app.post('/aitec/v1/cut-fill')
def cut_fill(x:CutFillInput, _:None=Depends(internal_token)):
    if not x.footprints:raise HTTPException(400,'footprints obrigatórios')
    try:fps=[shape(g) for g in x.footprints]
    except Exception as exc:raise HTTPException(400,f'footprint GeoJSON inválido: {exc}')
    c=fps[0].centroid;crs=utm_for_lon_lat(c.x,c.y);fwd=Transformer.from_crs(4326,crs,always_xy=True).transform
    samples=[]
    for s in x.terrain_samples:
        try:mx,my=fwd(float(s['longitude']),float(s['latitude']));samples.append({'x':mx,'y':my,'z':float(s['elevation_m'])})
        except Exception as exc:raise HTTPException(400,f'terrain sample inválido: {exc}')
    try:return {'projection':crs.to_string(),**estimate_cut_fill_from_samples([transform(fwd,g) for g in fps],samples)}
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/aitec/v1/building-solver')
def building_solver(x:BuildingStackInput, _:None=Depends(internal_token)):
    if not x.footprints:raise HTTPException(400,'footprints obrigatórios')
    try:fps=[shape(g) for g in x.footprints]
    except Exception as exc:raise HTTPException(400,f'footprint GeoJSON inválido: {exc}')
    c=fps[0].centroid;crs=utm_for_lon_lat(c.x,c.y);fwd=Transformer.from_crs(4326,crs,always_xy=True).transform;inv=Transformer.from_crs(crs,4326,always_xy=True).transform
    try:out=solve_building_stack([transform(fwd,g) for g in fps],x.floors,x.core_area_m2,x.circulation_width_m)
    except ValueError as exc:raise HTTPException(400,str(exc))
    serial={k:v for k,v in out.items() if k not in ('cores','circulations')};serial['cores']=[mapping(transform(inv,g)) for g in out.get('cores',[])];serial['circulations']=[mapping(transform(inv,g)) for g in out.get('circulations',[])];serial['projection']=crs.to_string();return serial

@app.post('/aitec/v1/site-solver')
def site_solver(x:SiteSolverInput, _:None=Depends(internal_token)):
    try:geom=shape(x.polygon)
    except Exception as exc:raise HTTPException(400,f'GeoJSON inválido: {exc}')
    if geom.geom_type not in ('Polygon','MultiPolygon') or geom.is_empty or not geom.is_valid:raise HTTPException(400,'É necessário Polygon/MultiPolygon GeoJSON válido.')
    if x.max_buildings<x.min_buildings:raise HTTPException(400,'max_buildings deve ser >= min_buildings')
    c=geom.centroid;crs=utm_for_lon_lat(c.x,c.y);fwd=Transformer.from_crs(4326,crs,always_xy=True).transform;inv=Transformer.from_crs(crs,4326,always_xy=True).transform;metric=transform(fwd,geom);inner=metric.buffer(-x.setback_m,join_style=2)
    if inner.is_empty:return {'status':'NO_VALID_ENVELOPE','reason':'setback_eliminates_buildable_area','parcel_area_m2':round(metric.area,2),'seed':x.seed,'items':[]}
    try:
        access_metric=transform(fwd,shape(x.access_point)) if x.access_point else None
        locked_metric=[transform(fwd,shape(g)) for g in x.locked_footprints]
        terrain_metric=[]
        for s in x.terrain_samples:
            mx,my=fwd(float(s['longitude']),float(s['latitude']));terrain_metric.append({'x':mx,'y':my,'z':float(s['elevation_m'])})
        solutions=generate_site_solutions(
            inner,float(metric.area),x.ca_max,x.to_max,x.tp_min,x.height_max_m,
            x.floor_height_m,x.efficiency,x.avg_unit_area_m2,x.min_buildings,x.max_buildings,
            x.min_spacing_m,x.spaces_per_unit,x.required_spaces,x.count,x.seed,
            x.stall_width_m,x.stall_length_m,x.aisle_width_m,
            parcel_geometry=metric,access_point=access_metric,access_required=x.access_required,road_width_m=x.road_width_m,
            unit_mix=x.unit_mix,min_total_units=x.min_total_units,terrain_samples=terrain_metric,
            core_area_m2=x.core_area_m2,circulation_width_m=x.circulation_width_m,locked_footprints=locked_metric,
        )
    except ValueError as exc:raise HTTPException(400,str(exc))
    serial=[]
    for sol in solutions:
        features=[];locked_count=int(sol.get('locked_count') or 0)
        for i,g in enumerate(sol.pop('footprints')):
            features.append({'type':'Feature','id':f"{sol['id']}-building-{i+1}",'geometry':mapping(transform(inv,g)),'properties':{'objectType':'BUILDING_FOOTPRINT','ordinal':i+1,'solutionId':sol['id'],'locked':i<locked_count}})
        for i,g in enumerate(sol.pop('parking_stalls',[])):
            features.append({'type':'Feature','id':f"{sol['id']}-parking-stall-{i+1}",'geometry':mapping(transform(inv,g)),'properties':{'objectType':'PARKING_STALL','ordinal':i+1,'solutionId':sol['id']}})
        for i,g in enumerate(sol.pop('parking_aisles',[])):
            features.append({'type':'Feature','id':f"{sol['id']}-drive-aisle-{i+1}",'geometry':mapping(transform(inv,g)),'properties':{'objectType':'DRIVE_AISLE','ordinal':i+1,'solutionId':sol['id']}})
        road=sol.get('road') or {};road_poly=road.pop('road',None);road_line=road.pop('centerline',None)
        if road_poly is not None:features.append({'type':'Feature','id':f"{sol['id']}-access-road-1",'geometry':mapping(transform(inv,road_poly)),'properties':{'objectType':'ACCESS_ROAD','ordinal':1,'solutionId':sol['id'],'roadWidthM':x.road_width_m}})
        if road_line is not None:features.append({'type':'Feature','id':f"{sol['id']}-road-centerline-1",'geometry':mapping(transform(inv,road_line)),'properties':{'objectType':'ROAD_CENTERLINE','ordinal':1,'solutionId':sol['id']}})
        building=sol.get('building') or {};cores=building.pop('cores',[]);circs=building.pop('circulations',[])
        for i,g in enumerate(cores):features.append({'type':'Feature','id':f"{sol['id']}-core-{i+1}",'geometry':mapping(transform(inv,g)),'properties':{'objectType':'BUILDING_CORE','ordinal':i+1,'solutionId':sol['id'],'floors':sol.get('metrics',{}).get('floors')}})
        for i,g in enumerate(circs):features.append({'type':'Feature','id':f"{sol['id']}-circulation-{i+1}",'geometry':mapping(transform(inv,g)),'properties':{'objectType':'CIRCULATION_ZONE','ordinal':i+1,'solutionId':sol['id'],'floors':sol.get('metrics',{}).get('floors')}})
        serial.append({**sol,'geometry':{'type':'FeatureCollection','features':features}})
    frontier=pareto_frontier(serial,{'estimated_net_area_m2':'MAX','tp_achieved':'MAX','parking_area_m2':'MIN'})
    valid=sum(1 for s in serial if not s.get('hard_invalid'))
    return {'status':'GENERATED' if serial else 'NO_SOLUTION_FOUND','solver_version':'site-solver-rc3','seed':x.seed,'projection':crs.to_string(),'requested_count':x.count,'generated_count':len(serial),'hard_valid_count':valid,'pareto_ids':[s['id'] for s in frontier],'envelope':{'setback_m':x.setback_m,'parcel_area_m2':round(metric.area,2),'buildable_area_m2':round(inner.area,2),'geometry':mapping(transform(inv,inner))},'items':serial,'limitations':['Site Solver RC3 adiciona acesso/viário conceitual, locks geométricos, unit mix por metas, cut/fill por amostras explícitas e core/circulação preliminares. Não substitui projeto viário, arquitetônico, estrutural, incêndio, geotécnico ou executivo.']}

@app.post('/aitec/v1/pareto')
def pareto(x:ParetoInput, _:None=Depends(internal_token)):
    if not x.weights:raise HTTPException(400,'weights obrigatórios')
    ranked=rank_scenarios(x.scenarios,x.weights)
    return {'status':'RANKED','items':ranked,'method':'weighted normalized score over hard-valid scenarios','limitations':['Ranking depende dos pesos explícitos do usuário; não transforma cenário inválido em válido.']}

@app.get('/metrics',include_in_schema=False)
def metrics():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse('# HELP lotediretor_service_up Service readiness\n# TYPE lotediretor_service_up gauge\nlotediretor_service_up{service="aitec-engine"} 1\n# HELP lotediretor_build_info Static build information\n# TYPE lotediretor_build_info gauge\nlotediretor_build_info{service="aitec-engine",version="19.0.0-rc.3"} 1\n',media_type='text/plain; version=0.0.4')
