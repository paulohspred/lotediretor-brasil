from __future__ import annotations
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel, Field
from math import acos, atan2, cos, degrees, pi, radians, sin
from datetime import datetime, timezone
import os
from .domain import SolarFinancialInput,RectObstacle,normalize_distribution,financial_projection,fit_panels,pack_rectangular_surface,monthly_energy_balance,electrical_string_design

app=FastAPI(title='LoteDiretor Solar Engine',version='19.0.0-rc.3')

def internal_token(x_internal_token:str|None=Header(default=None)):
    expected=os.getenv('INTERNAL_API_TOKEN','')
    if not expected or x_internal_token!=expected: raise HTTPException(403,'forbidden')

class Preliminary(BaseModel):
    panel_count:int=Field(gt=0,le=100000)
    panel_watts:float=Field(gt=0)
    specific_yield_kwh_per_kwp:float|None=Field(default=None,gt=0)

class Simulation(Preliminary):
    tariff_brl_per_kwh:float|None=Field(default=None,gt=0)
    capex_brl:float|None=Field(default=None,gt=0)
    annual_tariff_escalation:float=Field(default=0.04,ge=-0.5,le=1)
    annual_degradation:float=Field(default=0.005,ge=0,le=0.2)
    annual_om_brl:float=Field(default=0,ge=0)
    discount_rate:float=Field(default=0.10,ge=0,le=1)
    years:int=Field(default=25,ge=1,le=50)
    monthly_distribution:list[float]|None=None
    system_loss_fraction:float=Field(default=0.0,ge=0,lt=0.8)

class DesignInput(BaseModel):
    usable_area_m2:float=Field(gt=0)
    panel_width_m:float=Field(default=1.134,gt=0)
    panel_height_m:float=Field(default=2.278,gt=0)
    panel_watts:float=Field(default=550,gt=0)
    packing_factor:float=Field(default=0.82,gt=0,le=1)
    inverter_ac_kw:float|None=Field(default=None,gt=0)


class LayoutObstacle(BaseModel):
    x_m:float=Field(ge=0)
    y_m:float=Field(ge=0)
    width_m:float=Field(gt=0)
    height_m:float=Field(gt=0)
    clearance_m:float=Field(default=0,ge=0)

class LayoutInput(BaseModel):
    surface_width_m:float=Field(gt=0)
    surface_height_m:float=Field(gt=0)
    panel_width_m:float=Field(default=1.134,gt=0)
    panel_height_m:float=Field(default=2.278,gt=0)
    panel_watts:float=Field(default=550,gt=0)
    orientation:str='AUTO'
    edge_setback_m:float=Field(default=0.30,ge=0)
    panel_gap_m:float=Field(default=0.02,ge=0)
    aisle_every_rows:int|None=Field(default=None,ge=1)
    aisle_width_m:float=Field(default=0.60,ge=0)
    obstacles:list[LayoutObstacle]=Field(default_factory=list)

class EnergyBalanceInput(BaseModel):
    consumption_monthly_kwh:list[float]
    generation_monthly_kwh:list[float]

class SunPathInput(BaseModel):
    latitude:float=Field(ge=-90,le=90)
    longitude:float=Field(ge=-180,le=180)
    date_utc:str
    step_minutes:int=Field(default=60,ge=15,le=180)

class SunPosition(BaseModel):
    latitude:float=Field(ge=-90,le=90)
    longitude:float=Field(ge=-180,le=180)
    timestamp_utc:datetime

class ElectricalDesignInput(BaseModel):
    panel_count:int=Field(gt=0,le=1000000)
    module:dict
    inverter:dict
    temp_min_c:float=Field(ge=-80,le=80)
    temp_max_c:float=Field(ge=-40,le=120)

@app.get('/solar/health')
def health():return {'ok':True,'service':'solar-engine','version':'19.0.0-rc.3'}

@app.post('/solar/v1/preliminary')
def preliminary(x:Preliminary, _:None=Depends(internal_token)):
    kwp=x.panel_count*x.panel_watts/1000
    if x.specific_yield_kwh_per_kwp is None:
        return {'status':'requires_input','dc_kwp':kwp,'missing':['specific_yield_kwh_per_kwp'],'message':'No irradiation/yield assumption is invented by the engine.'}
    return {'status':'calculated_from_user_assumption','dc_kwp':kwp,'annual_kwh':kwp*x.specific_yield_kwh_per_kwp,'assumption':{'specific_yield_kwh_per_kwp':x.specific_yield_kwh_per_kwp}}

@app.post('/solar/v1/design')
def design(x:DesignInput, _:None=Depends(internal_token)):
    try:fit=fit_panels(x.usable_area_m2,x.panel_width_m,x.panel_height_m,x.packing_factor)
    except ValueError as exc:raise HTTPException(400,str(exc))
    dc_kwp=fit['max_panels']*x.panel_watts/1000
    dc_ac_ratio=(dc_kwp/x.inverter_ac_kw) if x.inverter_ac_kw else None
    return {'status':'PRELIMINARY','max_panels':fit['max_panels'],'dc_kwp':round(dc_kwp,3),'panel_area_m2':fit['panel_area_m2'],'usable_after_packing_m2':fit['usable_after_packing_m2'],'dc_ac_ratio':round(dc_ac_ratio,3) if dc_ac_ratio else None,'assumptions':x.model_dump(),'limitations':['O encaixe é por área agregada; orientação, obstáculos, corredores, sombreamento e layout elétrico exigem geometria do telhado.']}

@app.post('/solar/v1/simulation')
def simulation(x:Simulation, _:None=Depends(internal_token)):
    base=preliminary(x)
    if base['status']=='requires_input':return base
    gross_annual=float(base['annual_kwh']);annual=gross_annual*(1-x.system_loss_fraction)
    try:distribution=normalize_distribution(x.monthly_distribution)
    except ValueError as exc:raise HTTPException(400,str(exc))
    monthly=[round(annual*v,2) for v in distribution]
    financial={'finance':[],'simple_payback_year':None,'npv_brl':None,'lcoe_brl_per_kwh':None}
    if x.tariff_brl_per_kwh is not None and x.capex_brl is not None:
        financial=financial_projection(SolarFinancialInput(annual_kwh=annual,tariff_brl_per_kwh=x.tariff_brl_per_kwh,capex_brl=x.capex_brl,years=x.years,annual_tariff_escalation=x.annual_tariff_escalation,annual_degradation=x.annual_degradation,annual_om_brl=x.annual_om_brl,discount_rate=x.discount_rate))
    return {
        'status':'CALCULATED_FROM_INPUT_ASSUMPTIONS','dc_kwp':base['dc_kwp'],'gross_annual_kwh':round(gross_annual,2),'annual_kwh':round(annual,2),'monthly_kwh':monthly,
        **financial,
        'assumptions':{'specific_yield_kwh_per_kwp':x.specific_yield_kwh_per_kwp,'system_loss_fraction':x.system_loss_fraction,'tariff_brl_per_kwh':x.tariff_brl_per_kwh,'capex_brl':x.capex_brl,'annual_om_brl':x.annual_om_brl,'discount_rate':x.discount_rate,'annual_tariff_escalation':x.annual_tariff_escalation,'annual_degradation':x.annual_degradation},
        'limitations':['Não inclui sombreamento 3D, clipping por inversor, tarifa horária, tributos ou regras locais se não forem fornecidos.','specific_yield_kwh_per_kwp continua sendo uma premissa externa e deve ter fonte/calibração para uso técnico.']
    }


@app.post('/solar/v1/layout-2d')
def layout_2d(x:LayoutInput, _:None=Depends(internal_token)):
    try:
        out=pack_rectangular_surface(x.surface_width_m,x.surface_height_m,x.panel_width_m,x.panel_height_m,x.orientation,x.edge_setback_m,x.panel_gap_m,x.aisle_every_rows,x.aisle_width_m,[RectObstacle(**o.model_dump()) for o in x.obstacles])
    except ValueError as exc:raise HTTPException(400,str(exc))
    out['dc_kwp']=round(out['panel_count']*x.panel_watts/1000,3)
    out['engine_version']='19.0.0-rc.3'
    out['status']='PRELIMINARY_2D'
    out['limitations']=['Layout em frame local métrico e superfície retangular; não substitui levantamento do telhado.','Obstáculos são retângulos fornecidos; não há inferência automática por imagem nesta release.','Não inclui strings, capacidade estrutural, clipping, sombreamento 3D ou aprovação de conexão.']
    return out

@app.post('/solar/v1/electrical-string-design')
def electrical_design(x:ElectricalDesignInput, _:None=Depends(internal_token)):
    try:return electrical_string_design(x.panel_count,x.module,x.inverter,x.temp_min_c,x.temp_max_c)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/solar/v1/energy-balance')
def energy_balance(x:EnergyBalanceInput, _:None=Depends(internal_token)):
    try:out=monthly_energy_balance(x.consumption_monthly_kwh,x.generation_monthly_kwh)
    except ValueError as exc:raise HTTPException(400,str(exc))
    return {'status':'CALCULATED_FROM_MONTHLY_SERIES',**out,'limitations':['Compensação financeira/regulatória não é inferida a partir do balanço energético.']}

@app.post('/solar/v1/sun-path')
def sun_path(x:SunPathInput, _:None=Depends(internal_token)):
    try:day=datetime.fromisoformat(x.date_utc).date()
    except Exception:raise HTTPException(400,'date_utc must be ISO date')
    pts=[]
    for minute in range(0,24*60,x.step_minutes):
        dt=datetime(day.year,day.month,day.day,minute//60,minute%60,tzinfo=timezone.utc)
        pos=sun_position(SunPosition(latitude=x.latitude,longitude=x.longitude,timestamp_utc=dt),None)
        if pos['solar_elevation_deg']>-6:pts.append(pos)
    return {'status':'PRELIMINARY','date_utc':day.isoformat(),'points':pts,'method':'NOAA approximation','limitations':['Trajetória não inclui horizonte local, relevo ou obstáculos.']}

@app.post('/solar/v1/sun-position')
def sun_position(x:SunPosition, _:None=Depends(internal_token)):
    dt=x.timestamp_utc.astimezone(timezone.utc);n=dt.timetuple().tm_yday;hour=dt.hour+dt.minute/60+dt.second/3600
    gamma=2*pi/365*(n-1+(hour-12)/24);decl=(0.006918-0.399912*cos(gamma)+0.070257*sin(gamma)-0.006758*cos(2*gamma)+0.000907*sin(2*gamma)-0.002697*cos(3*gamma)+0.00148*sin(3*gamma));eqtime=229.18*(0.000075+0.001868*cos(gamma)-0.032077*sin(gamma)-0.014615*cos(2*gamma)-0.040849*sin(2*gamma));true_solar_minutes=hour*60+eqtime+4*x.longitude;ha=radians(true_solar_minutes/4-180);lat=radians(x.latitude);cos_zen=max(-1,min(1,sin(lat)*sin(decl)+cos(lat)*cos(decl)*cos(ha)));zen=acos(cos_zen);elevation=90-degrees(zen);az=degrees(atan2(sin(ha),cos(ha)*sin(lat)-sin(decl)/max(cos(decl)*cos(lat),1e-12)))+180
    return {'status':'PRELIMINARY','timestamp_utc':dt.isoformat(),'solar_elevation_deg':round(elevation,3),'solar_azimuth_deg':round(az%360,3),'method':'NOAA approximation','limitations':['Posição solar preliminar; simulação de projeto deve usar modelo calibrado e horizonte/sombreamento.']}

@app.get('/metrics',include_in_schema=False)
def metrics():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse('# HELP lotediretor_service_up Service readiness\n# TYPE lotediretor_service_up gauge\nlotediretor_service_up{service="solar-engine"} 1\n# HELP lotediretor_build_info Static build information\n# TYPE lotediretor_build_info gauge\nlotediretor_build_info{service="solar-engine",version="19.0.0-rc.3"} 1\n',media_type='text/plain; version=0.0.4')
