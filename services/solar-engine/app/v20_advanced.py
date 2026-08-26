from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from .v20 import SOLAR_V20_VERSION


def _finite(value: Any, name: str) -> float:
    out=float(value)
    if not math.isfinite(out): raise ValueError(f'{name} must be finite')
    return out


def solar_position(latitude_deg: float, longitude_deg: float, timestamp_iso: str) -> dict:
    """Approximate NOAA solar position from an offset-aware timestamp.

    The result is deterministic and suitable for preliminary geometry/shadow
    studies. It deliberately does not claim survey/metrology-grade ephemeris.
    """
    lat=_finite(latitude_deg,'latitude_deg');lon=_finite(longitude_deg,'longitude_deg')
    if not -90<=lat<=90: raise ValueError('latitude_deg must be in [-90,90]')
    if not -180<=lon<=180: raise ValueError('longitude_deg must be in [-180,180]')
    try: dt=datetime.fromisoformat(str(timestamp_iso).replace('Z','+00:00'))
    except Exception as exc: raise ValueError('timestamp_iso must be ISO-8601') from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        return {'status':'REQUIRES_INPUT','missing':['timestamp_iso.utc_offset']}
    day=dt.timetuple().tm_yday
    hour=dt.hour+dt.minute/60+dt.second/3600+dt.microsecond/3_600_000_000
    gamma=2*math.pi/365*(day-1+(hour-12)/24)
    eqtime=229.18*(0.000075+0.001868*math.cos(gamma)-0.032077*math.sin(gamma)-0.014615*math.cos(2*gamma)-0.040849*math.sin(2*gamma))
    decl=(0.006918-0.399912*math.cos(gamma)+0.070257*math.sin(gamma)-0.006758*math.cos(2*gamma)+0.000907*math.sin(2*gamma)-0.002697*math.cos(3*gamma)+0.00148*math.sin(3*gamma))
    offset_min=dt.utcoffset().total_seconds()/60
    true_solar_min=(hour*60+eqtime+4*lon-offset_min)%1440
    hour_angle=true_solar_min/4-180
    ha=math.radians(hour_angle);phi=math.radians(lat)
    cos_zen=max(-1.0,min(1.0,math.sin(phi)*math.sin(decl)+math.cos(phi)*math.cos(decl)*math.cos(ha)))
    zen=math.degrees(math.acos(cos_zen));elev=90-zen
    # Azimuth clockwise from geographic north.
    az=(math.degrees(math.atan2(math.sin(ha),math.cos(ha)*math.sin(phi)-math.tan(decl)*math.cos(phi)))+180)%360
    return {
        'status':'CALCULATED_SOLAR_POSITION_APPROXIMATE','solver_version':SOLAR_V20_VERSION,
        'timestamp_iso':dt.isoformat(),'latitude_deg':lat,'longitude_deg':lon,
        'azimuth_deg':round(az,6),'elevation_deg':round(elev,6),'zenith_deg':round(zen,6),
        'declination_deg':round(math.degrees(decl),6),'equation_of_time_min':round(eqtime,6),
        'direct_sun_above_horizon':elev>0,
        'limitations':['NOAA-style analytical approximation; atmospheric refraction, terrain horizon and high-precision ephemeris are not modeled.'],
    }


def plane_of_array_irradiance(ghi_w_m2: float, dni_w_m2: float, dhi_w_m2: float, solar_zenith_deg: float, solar_azimuth_deg: float, surface_tilt_deg: float, surface_azimuth_deg: float, albedo: float) -> dict:
    ghi=_finite(ghi_w_m2,'ghi_w_m2');dni=_finite(dni_w_m2,'dni_w_m2');dhi=_finite(dhi_w_m2,'dhi_w_m2')
    if min(ghi,dni,dhi)<0: raise ValueError('irradiance components must be non-negative')
    zen=_finite(solar_zenith_deg,'solar_zenith_deg');saz=_finite(solar_azimuth_deg,'solar_azimuth_deg')%360
    tilt=_finite(surface_tilt_deg,'surface_tilt_deg');paz=_finite(surface_azimuth_deg,'surface_azimuth_deg')%360
    alb=_finite(albedo,'albedo')
    if not 0<=zen<=180 or not 0<=tilt<=180: raise ValueError('zenith/tilt must be in [0,180]')
    if not 0<=alb<=1: raise ValueError('albedo must be in [0,1]')
    z=math.radians(zen);b=math.radians(tilt);delta=math.radians(saz-paz)
    cos_inc=math.cos(z)*math.cos(b)+math.sin(z)*math.sin(b)*math.cos(delta)
    beam=dni*max(0.0,cos_inc)
    sky=dhi*(1+math.cos(b))/2
    ground=ghi*alb*(1-math.cos(b))/2
    poa=beam+sky+ground
    return {
        'status':'CALCULATED_ISOTROPIC_POA','solver_version':SOLAR_V20_VERSION,
        'poa_global_w_m2':round(poa,6),'poa_beam_w_m2':round(beam,6),'poa_sky_diffuse_w_m2':round(sky,6),'poa_ground_diffuse_w_m2':round(ground,6),
        'incidence_cosine':round(cos_inc,8),'surface_tilt_deg':tilt,'surface_azimuth_deg':paz,'albedo':alb,
        'limitations':['Modelo isotrópico de céu; recurso GHI/DNI/DHI deve vir de snapshot identificado e calibração independente é obrigatória para homologação.'],
    }


def roof_rect_layout(surface_width_m: float, surface_depth_m: float, module_width_m: float, module_length_m: float, setback_m: float, row_gap_m: float, column_gap_m: float, orientation: str, excluded_rectangles: list[dict] | None=None) -> dict:
    sw=_finite(surface_width_m,'surface_width_m');sd=_finite(surface_depth_m,'surface_depth_m')
    mw=_finite(module_width_m,'module_width_m');ml=_finite(module_length_m,'module_length_m')
    setback=_finite(setback_m,'setback_m');rg=_finite(row_gap_m,'row_gap_m');cg=_finite(column_gap_m,'column_gap_m')
    if min(sw,sd,mw,ml)<=0 or min(setback,rg,cg)<0: raise ValueError('surface/module dimensions must be positive and gaps/setback non-negative')
    mode=str(orientation).upper()
    if mode not in ('PORTRAIT','LANDSCAPE'): raise ValueError('orientation must be PORTRAIT or LANDSCAPE')
    pw,pd=(mw,ml) if mode=='PORTRAIT' else (ml,mw)
    usable_w=sw-2*setback;usable_d=sd-2*setback
    if usable_w<pw or usable_d<pd:
        return {'status':'NO_PANEL_FITS','solver_version':SOLAR_V20_VERSION,'panel_count':0,'panels':[]}
    exclusions=[]
    for i,r in enumerate(excluded_rectangles or []):
        try: x=float(r['x_m']);y=float(r['y_m']);w=float(r['width_m']);d=float(r['depth_m'])
        except Exception as exc: raise ValueError(f'excluded_rectangles[{i}] requires x_m/y_m/width_m/depth_m') from exc
        if min(w,d)<0: raise ValueError('excluded rectangle dimensions must be non-negative')
        exclusions.append((x,y,x+w,y+d))
    def intersects(x1,y1,x2,y2):
        return any(not (x2<=ex1 or x1>=ex2 or y2<=ey1 or y1>=ey2) for ex1,ey1,ex2,ey2 in exclusions)
    panels=[];y=setback;row=0
    while y+pd<=sd-setback+1e-9:
        x=setback;col=0
        while x+pw<=sw-setback+1e-9:
            if not intersects(x,y,x+pw,y+pd):
                panels.append({'id':f'P-{len(panels)+1:05d}','row':row,'column':col,'x_m':round(x,4),'y_m':round(y,4),'width_m':pw,'depth_m':pd,'geometry':{'type':'Polygon','coordinates':[[[x,y],[x+pw,y],[x+pw,y+pd],[x,y+pd],[x,y]]]}})
            x+=pw+cg;col+=1
        y+=pd+rg;row+=1
    return {
        'status':'PRELIMINARY_ROOF_LAYOUT','solver_version':SOLAR_V20_VERSION,'orientation':mode,'panel_count':len(panels),'panels':panels,
        'surface_area_m2':round(sw*sd,4),'module_footprint_m2':round(pw*pd,4),'packing_coverage_fraction':round(len(panels)*pw*pd/(sw*sd),6),
        'setback_m':setback,'row_gap_m':rg,'column_gap_m':cg,'excluded_rectangle_count':len(exclusions),
        'limitations':['Packing retangular local; não resolve polígonos arbitrários, estrutura, passarelas normativas específicas ou sombreamento entre módulos.'],
    }


def string_mppt_design(module: dict, inverter: dict, module_count: int, temp_min_c: float, temp_max_c: float) -> dict:
    mreq=('pmax_w','voc_stc_v','vmp_stc_v','isc_stc_a','imp_stc_a','voc_temp_coeff_pct_per_c','vmp_temp_coeff_pct_per_c')
    ireq=('max_dc_voltage_v','mppt_min_v','mppt_max_v','max_input_current_a_per_mppt','mppt_count','max_ac_power_kw')
    mm=[x for x in mreq if module.get(x) is None];ii=[x for x in ireq if inverter.get(x) is None]
    if mm or ii: return {'status':'REQUIRES_INPUT','missing':[f'module.{x}' for x in mm]+[f'inverter.{x}' for x in ii]}
    count=int(module_count);tmin=_finite(temp_min_c,'temp_min_c');tmax=_finite(temp_max_c,'temp_max_c')
    if count<=0 or tmin>tmax: raise ValueError('module_count must be > 0 and temp_min_c <= temp_max_c')
    pmax=float(module['pmax_w']);voc=float(module['voc_stc_v']);vmp=float(module['vmp_stc_v']);isc=float(module['isc_stc_a']);imp=float(module['imp_stc_a'])
    voc_tc=float(module['voc_temp_coeff_pct_per_c'])/100;vmp_tc=float(module['vmp_temp_coeff_pct_per_c'])/100
    maxdc=float(inverter['max_dc_voltage_v']);mppt_min=float(inverter['mppt_min_v']);mppt_max=float(inverter['mppt_max_v']);max_i=float(inverter['max_input_current_a_per_mppt']);mppts=int(inverter['mppt_count']);ac_kw=float(inverter['max_ac_power_kw'])
    if min(pmax,voc,vmp,isc,imp,maxdc,mppt_min,mppt_max,max_i,mppts,ac_kw)<=0: raise ValueError('electrical values must be > 0')
    if mppt_min>mppt_max: raise ValueError('mppt_min_v must be <= mppt_max_v')
    voc_cold=voc*(1+voc_tc*(tmin-25));vmp_hot=vmp*(1+vmp_tc*(tmax-25));vmp_cold=vmp*(1+vmp_tc*(tmin-25))
    if min(voc_cold,vmp_hot,vmp_cold)<=0: raise ValueError('temperature coefficients produce non-positive voltage')
    min_series=max(1,math.ceil(mppt_min/vmp_hot))
    max_series=min(math.floor(maxdc/voc_cold),math.floor(mppt_max/vmp_cold))
    strings_per_mppt=max(0,math.floor(max_i/isc));max_strings=mppts*strings_per_mppt
    if max_series<min_series or max_strings<1:
        return {'status':'NO_FEASIBLE_STRING_CONFIGURATION','solver_version':SOLAR_V20_VERSION,'series_range':{'min':min_series,'max':max_series},'max_strings':max_strings}
    candidates=[]
    for series in range(min_series,max_series+1):
        strings=min(max_strings,count//series)
        if strings<1: continue
        used=series*strings
        candidates.append((used,series,strings))
    if not candidates:
        return {'status':'NO_FEASIBLE_STRING_CONFIGURATION','solver_version':SOLAR_V20_VERSION,'series_range':{'min':min_series,'max':max_series},'max_strings':max_strings}
    used,series,strings=max(candidates,key=lambda x:(x[0],x[1],-x[2]))
    distribution=[strings//mppts+(1 if i<strings%mppts else 0) for i in range(mppts)]
    dc_kw=used*pmax/1000
    return {
        'status':'ELECTRICAL_DESIGN_OK' if used==count else 'ELECTRICAL_DESIGN_PARTIAL','solver_version':SOLAR_V20_VERSION,
        'requested_module_count':count,'used_module_count':used,'unallocated_module_count':count-used,'modules_per_string':series,'string_count':strings,
        'strings_per_mppt':distribution,'series_range':{'min':min_series,'max':max_series},'max_parallel_strings_per_mppt':strings_per_mppt,
        'temperature_adjusted':{'voc_module_cold_v':round(voc_cold,4),'vmp_module_hot_v':round(vmp_hot,4),'vmp_module_cold_v':round(vmp_cold,4),'string_voc_cold_v':round(voc_cold*series,4),'string_vmp_hot_v':round(vmp_hot*series,4)},
        'dc_power_kw':round(dc_kw,4),'ac_power_kw':ac_kw,'dc_ac_ratio':round(dc_kw/ac_kw,6),'mppt_string_current_a':round(isc*max(distribution or [0]),4),
        'clipping_simulation_required':True,
        'limitations':['Dimensionamento elétrico preliminar por limites informados; proteção, cabo, norma, curva IV, mismatch e clipping horário exigem engenharia/modelo específico.'],
    }


def financial_projection(capex_brl: float, annual_generation_kwh: float, energy_value_brl_per_kwh: float, years: int, discount_rate: float, annual_degradation: float, energy_value_escalation: float, annual_opex_brl: float, opex_escalation: float, replacements: list[dict]) -> dict:
    capex=_finite(capex_brl,'capex_brl');generation=_finite(annual_generation_kwh,'annual_generation_kwh');value=_finite(energy_value_brl_per_kwh,'energy_value_brl_per_kwh')
    n=int(years);disc=_finite(discount_rate,'discount_rate');deg=_finite(annual_degradation,'annual_degradation');vesc=_finite(energy_value_escalation,'energy_value_escalation');opex=_finite(annual_opex_brl,'annual_opex_brl');oesc=_finite(opex_escalation,'opex_escalation')
    if capex<0 or generation<0 or value<0 or opex<0 or n<1: raise ValueError('financial base values must be non-negative and years >= 1')
    if disc<=-1 or not 0<=deg<1 or vesc<=-1 or oesc<=-1: raise ValueError('invalid financial rates')
    replacement_by_year={}
    for i,item in enumerate(replacements or []):
        if item.get('year') is None or item.get('cost_brl') is None: return {'status':'REQUIRES_INPUT','missing':[f'replacements[{i}].year',f'replacements[{i}].cost_brl']}
        year=int(item['year']);cost=float(item['cost_brl'])
        if year<1 or year>n or cost<0: raise ValueError('replacement year/cost outside projection')
        replacement_by_year[year]=replacement_by_year.get(year,0.0)+cost
    cashflows=[-capex];rows=[];cumulative=-capex;simple_payback=None;discounted_cumulative=-capex;discounted_payback=None
    for year in range(1,n+1):
        gen=generation*((1-deg)**(year-1));unit=value*((1+vesc)**(year-1));gross=gen*unit;op=opex*((1+oesc)**(year-1));repl=replacement_by_year.get(year,0.0);net=gross-op-repl
        cashflows.append(net);cumulative+=net;discounted=net/((1+disc)**year);discounted_cumulative+=discounted
        if simple_payback is None and cumulative>=0: simple_payback=year
        if discounted_payback is None and discounted_cumulative>=0: discounted_payback=year
        rows.append({'year':year,'generation_kwh':round(gen,2),'energy_value_brl_per_kwh':round(unit,6),'gross_benefit_brl':round(gross,2),'opex_brl':round(op,2),'replacement_brl':round(repl,2),'net_cashflow_brl':round(net,2),'discounted_cashflow_brl':round(discounted,2)})
    npv=sum(cf/((1+disc)**i) for i,cf in enumerate(cashflows))
    def npv_at(rate): return sum(cf/((1+rate)**i) for i,cf in enumerate(cashflows))
    irr=None
    lo,hi=-0.9999,10.0
    flo,fhi=npv_at(lo),npv_at(hi)
    if flo==0: irr=lo
    elif fhi==0: irr=hi
    elif flo*fhi<0:
        for _ in range(120):
            mid=(lo+hi)/2;fm=npv_at(mid)
            if abs(fm)<1e-8: lo=hi=mid;break
            if flo*fm<=0: hi=mid;fhi=fm
            else: lo=mid;flo=fm
        irr=(lo+hi)/2
    return {
        'status':'CALCULATED_EXPLICIT_FINANCIAL_PROJECTION','solver_version':SOLAR_V20_VERSION,'years':n,'cashflows':rows,
        'npv_brl':round(npv,2),'irr':None if irr is None else round(irr,8),'simple_payback_year':simple_payback,'discounted_payback_year':discounted_payback,
        'assumptions':{'capex_brl':capex,'annual_generation_kwh_year1':generation,'energy_value_brl_per_kwh_year1':value,'discount_rate':disc,'annual_degradation':deg,'energy_value_escalation':vesc,'annual_opex_brl_year1':opex,'opex_escalation':oesc,'replacements':replacements},
        'limitations':['Projeção determinística sobre premissas explícitas; não representa proposta comercial, previsão tarifária garantida, imposto, financiamento ou garantia de retorno.'],
    }
