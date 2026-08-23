from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class SolarFinancialInput:
    annual_kwh: float
    tariff_brl_per_kwh: float
    capex_brl: float
    years: int = 25
    annual_tariff_escalation: float = 0.04
    annual_degradation: float = 0.005
    annual_om_brl: float = 0.0
    discount_rate: float = 0.10


def normalize_distribution(values:list[float]|None)->list[float]:
    default=[0.075,0.073,0.078,0.075,0.072,0.067,0.069,0.076,0.086,0.091,0.083,0.075]
    vals=values or default
    if len(vals)!=12 or any(v<0 for v in vals):
        raise ValueError('monthly_distribution must contain 12 non-negative values')
    total=sum(vals)
    if total<=0:raise ValueError('monthly_distribution sum must be > 0')
    return [v/total for v in vals]


def financial_projection(x:SolarFinancialInput):
    cumulative=-x.capex_brl
    discounted_cumulative=-x.capex_brl
    payback_year=None
    npv=-x.capex_brl
    finance=[]
    lifetime_generation=0.0
    lifetime_cost=x.capex_brl
    for year in range(1,x.years+1):
        generation=x.annual_kwh*((1-x.annual_degradation)**(year-1))
        tariff=x.tariff_brl_per_kwh*((1+x.annual_tariff_escalation)**(year-1))
        gross=generation*tariff
        net=gross-x.annual_om_brl
        cumulative+=net
        discount=(1+x.discount_rate)**year
        discounted=net/discount
        npv+=discounted
        discounted_cumulative+=discounted
        lifetime_generation+=generation
        lifetime_cost+=x.annual_om_brl/discount
        if payback_year is None and cumulative>=0:payback_year=year
        finance.append({
            'year':year,'generation_kwh':round(generation,2),'tariff_brl_per_kwh':round(tariff,4),
            'gross_savings_brl':round(gross,2),'om_brl':round(x.annual_om_brl,2),'net_cashflow_brl':round(net,2),
            'discounted_cashflow_brl':round(discounted,2),'cumulative_after_capex_brl':round(cumulative,2)
        })
    lcoe=(lifetime_cost/lifetime_generation) if lifetime_generation>0 else None
    return {'finance':finance,'simple_payback_year':payback_year,'npv_brl':round(npv,2),'lcoe_brl_per_kwh':round(lcoe,4) if lcoe is not None else None,'discounted_cumulative_brl':round(discounted_cumulative,2)}


def fit_panels(usable_area_m2:float,panel_width_m:float,panel_height_m:float,packing_factor:float=0.82):
    if usable_area_m2<=0 or panel_width_m<=0 or panel_height_m<=0:raise ValueError('areas/dimensions must be positive')
    if not 0<packing_factor<=1:raise ValueError('packing_factor must be in (0,1]')
    panel_area=panel_width_m*panel_height_m
    max_panels=int((usable_area_m2*packing_factor)//panel_area)
    return {'panel_area_m2':round(panel_area,4),'usable_after_packing_m2':round(usable_area_m2*packing_factor,2),'max_panels':max_panels}

@dataclass(frozen=True)
class RectObstacle:
    x_m: float
    y_m: float
    width_m: float
    height_m: float
    clearance_m: float = 0.0


def _rects_overlap(a:dict,b:dict)->bool:
    return not (
        a['x_m'] + a['width_m'] <= b['x_m'] or
        b['x_m'] + b['width_m'] <= a['x_m'] or
        a['y_m'] + a['height_m'] <= b['y_m'] or
        b['y_m'] + b['height_m'] <= a['y_m']
    )


def pack_rectangular_surface(
    width_m:float,
    height_m:float,
    panel_width_m:float,
    panel_height_m:float,
    orientation:str='AUTO',
    edge_setback_m:float=0.30,
    panel_gap_m:float=0.02,
    aisle_every_rows:int|None=None,
    aisle_width_m:float=0.60,
    obstacles:list[RectObstacle]|None=None,
):
    """Deterministic 2D packing in a local metric frame.

    This is deliberately a preliminary layout engine. It does not infer roof
    geometry, structural capacity, electrical strings or 3D shadows.
    """
    if min(width_m,height_m,panel_width_m,panel_height_m)<=0:
        raise ValueError('surface and panel dimensions must be positive')
    if edge_setback_m<0 or panel_gap_m<0 or aisle_width_m<0:
        raise ValueError('setbacks/gaps must be non-negative')
    if width_m <= 2*edge_setback_m or height_m <= 2*edge_setback_m:
        return {'orientation':'PORTRAIT','panels':[],'panel_count':0,'used_area_m2':0.0,'coverage_ratio':0.0}
    obstacle_rects=[]
    for o in obstacles or []:
        c=max(0.0,float(o.clearance_m))
        obstacle_rects.append({'x_m':o.x_m-c,'y_m':o.y_m-c,'width_m':o.width_m+2*c,'height_m':o.height_m+2*c})

    def place(ori:str):
        pw,ph=(panel_width_m,panel_height_m) if ori=='PORTRAIT' else (panel_height_m,panel_width_m)
        panels=[];row=0;y=edge_setback_m;ordinal=1
        max_x=width_m-edge_setback_m;max_y=height_m-edge_setback_m
        while y+ph <= max_y+1e-9:
            if row>0 and aisle_every_rows and aisle_every_rows>0 and row % aisle_every_rows==0:
                y+=aisle_width_m
                if y+ph>max_y+1e-9:break
            x=edge_setback_m
            while x+pw <= max_x+1e-9:
                candidate={'ordinal':ordinal,'x_m':round(x,4),'y_m':round(y,4),'width_m':round(pw,4),'height_m':round(ph,4),'rotation_deg':0 if ori=='PORTRAIT' else 90}
                if not any(_rects_overlap(candidate,o) for o in obstacle_rects):
                    panels.append(candidate);ordinal+=1
                x+=pw+panel_gap_m
            y+=ph+panel_gap_m;row+=1
        surface_area=width_m*height_m;used=len(panels)*panel_width_m*panel_height_m
        return {'orientation':ori,'panels':panels,'panel_count':len(panels),'used_area_m2':round(used,3),'coverage_ratio':round(used/surface_area,4),'surface_area_m2':round(surface_area,3)}

    ori=orientation.strip().upper()
    if ori not in ('AUTO','PORTRAIT','LANDSCAPE'):raise ValueError('orientation must be AUTO, PORTRAIT or LANDSCAPE')
    if ori!='AUTO':return place(ori)
    a,b=place('PORTRAIT'),place('LANDSCAPE')
    return b if b['panel_count']>a['panel_count'] else a


def monthly_energy_balance(consumption_kwh:list[float],generation_kwh:list[float]):
    if len(consumption_kwh)!=12 or len(generation_kwh)!=12:
        raise ValueError('consumption and generation must contain 12 monthly values')
    if any(float(x)<0 for x in consumption_kwh+generation_kwh):
        raise ValueError('monthly energy values must be non-negative')
    consumption=[float(x) for x in consumption_kwh];generation=[float(x) for x in generation_kwh]
    self_consumption=[min(c,g) for c,g in zip(consumption,generation)]
    injected=[max(g-c,0.0) for c,g in zip(consumption,generation)]
    grid_purchase=[max(c-g,0.0) for c,g in zip(consumption,generation)]
    total_g=sum(generation);total_c=sum(consumption);total_self=sum(self_consumption)
    return {
      'consumption_monthly_kwh':[round(x,2) for x in consumption],
      'generation_monthly_kwh':[round(x,2) for x in generation],
      'self_consumption_monthly_kwh':[round(x,2) for x in self_consumption],
      'injected_monthly_kwh':[round(x,2) for x in injected],
      'grid_purchase_monthly_kwh':[round(x,2) for x in grid_purchase],
      'annual_consumption_kwh':round(total_c,2),'annual_generation_kwh':round(total_g,2),
      'annual_self_consumption_kwh':round(total_self,2),'annual_injected_kwh':round(sum(injected),2),'annual_grid_purchase_kwh':round(sum(grid_purchase),2),
      'self_consumption_ratio':round(total_self/total_g,4) if total_g>0 else None,
      'self_sufficiency_ratio':round(total_self/total_c,4) if total_c>0 else None,
    }


def electrical_string_design(
    panel_count:int,
    module:dict,
    inverter:dict,
    temp_min_c:float,
    temp_max_c:float,
):
    """Preliminary string/MPPT sizing from explicit datasheet values only.

    Required module fields: watts, voc_v, vmp_v, isc_a, imp_a,
    temp_coeff_voc_pct_per_c, temp_coeff_vmp_pct_per_c.
    Required inverter fields: ac_kw, max_dc_kw, mppt_count, mppt_min_v,
    mppt_max_v, max_dc_v, max_input_current_a_per_mppt.
    No NEC/ABNT safety multiplier, cable sizing or manufacturer-specific rule is
    invented here; those remain external engineering checks.
    """
    import math
    if panel_count<=0:raise ValueError('panel_count must be > 0')
    required_module=('watts','voc_v','vmp_v','isc_a','imp_a','temp_coeff_voc_pct_per_c','temp_coeff_vmp_pct_per_c')
    required_inverter=('ac_kw','max_dc_kw','mppt_count','mppt_min_v','mppt_max_v','max_dc_v','max_input_current_a_per_mppt')
    missing=[f'module.{k}' for k in required_module if module.get(k) is None]+[f'inverter.{k}' for k in required_inverter if inverter.get(k) is None]
    if missing:return {'status':'REQUIRES_INPUT','missing':missing,'message':'Electrical design is not calculated without explicit datasheet values.'}
    try:
        m={k:float(module[k]) for k in required_module if k not in ('temp_coeff_voc_pct_per_c','temp_coeff_vmp_pct_per_c')}
        m['temp_coeff_voc_pct_per_c']=float(module['temp_coeff_voc_pct_per_c']);m['temp_coeff_vmp_pct_per_c']=float(module['temp_coeff_vmp_pct_per_c'])
        inv={k:float(inverter[k]) for k in required_inverter if k!='mppt_count'};inv['mppt_count']=int(inverter['mppt_count'])
    except Exception as exc:raise ValueError(f'invalid electrical datasheet value: {exc}')
    if min(m['watts'],m['voc_v'],m['vmp_v'],m['isc_a'],m['imp_a'],inv['ac_kw'],inv['max_dc_kw'],inv['mppt_count'],inv['mppt_min_v'],inv['mppt_max_v'],inv['max_dc_v'],inv['max_input_current_a_per_mppt'])<=0:
        raise ValueError('electrical datasheet values must be positive')
    if temp_min_c>temp_max_c:raise ValueError('temp_min_c must be <= temp_max_c')
    voc_cold=m['voc_v']*(1+m['temp_coeff_voc_pct_per_c']/100*(temp_min_c-25))
    vmp_hot=m['vmp_v']*(1+m['temp_coeff_vmp_pct_per_c']/100*(temp_max_c-25))
    vmp_cold=m['vmp_v']*(1+m['temp_coeff_vmp_pct_per_c']/100*(temp_min_c-25))
    if min(voc_cold,vmp_hot,vmp_cold)<=0:return {'status':'INVALID_DATASHEET_OR_TEMPERATURE','reason':'temperature_adjusted_voltage_non_positive'}
    min_series=max(1,math.ceil(inv['mppt_min_v']/vmp_hot))
    max_series=min(math.floor(inv['max_dc_v']/voc_cold),math.floor(inv['mppt_max_v']/vmp_cold))
    if max_series<min_series:
        return {'status':'NO_VALID_STRING_LENGTH','min_modules_per_string':min_series,'max_modules_per_string':max_series,'temperature_adjusted':{'voc_cold_v':round(voc_cold,3),'vmp_hot_v':round(vmp_hot,3),'vmp_cold_v':round(vmp_cold,3)}}
    max_parallel=max(1,math.floor(inv['max_input_current_a_per_mppt']/m['isc_a']))
    total_parallel_capacity=inv['mppt_count']*max_parallel
    best=None
    for strings in range(1,total_parallel_capacity+1):
        base=panel_count//strings;extra=panel_count%strings
        counts=[base+1 if i<extra else base for i in range(strings)]
        if min(counts)<min_series or max(counts)>max_series:continue
        # Spread strings over MPPTs as evenly as possible.
        mppt_loads=[0]*inv['mppt_count']
        for i in range(strings):mppt_loads[i%inv['mppt_count']]+=1
        if max(mppt_loads)>max_parallel:continue
        imbalance=max(counts)-min(counts)
        score=(imbalance,strings,-min(counts))
        if best is None or score<best[0]:best=(score,counts,mppt_loads)
    dc_kwp=panel_count*m['watts']/1000
    dc_ac_ratio=dc_kwp/inv['ac_kw']
    if best is None:
        return {'status':'NO_VALID_STRING_DISTRIBUTION','dc_kwp':round(dc_kwp,3),'dc_ac_ratio':round(dc_ac_ratio,3),'min_modules_per_string':min_series,'max_modules_per_string':max_series,'max_parallel_strings_per_mppt':max_parallel,'mppt_count':inv['mppt_count'],'temperature_adjusted':{'voc_cold_v':round(voc_cold,3),'vmp_hot_v':round(vmp_hot,3),'vmp_cold_v':round(vmp_cold,3)}}
    _,counts,mppt_loads=best
    strings=[]
    for i,n in enumerate(counts):
        strings.append({'string':i+1,'mppt':i%inv['mppt_count']+1,'modules':n,'voc_cold_v':round(n*voc_cold,2),'vmp_hot_v':round(n*vmp_hot,2),'vmp_cold_v':round(n*vmp_cold,2),'imp_a':round(m['imp_a'],3),'isc_a':round(m['isc_a'],3)})
    checks=[]
    for st in strings:
        checks.extend([
            {'code':f"STRING_{st['string']}_MAX_DC_V",'status':'PASS' if st['voc_cold_v']<=inv['max_dc_v']+1e-9 else 'FAIL','observed':st['voc_cold_v'],'limit':inv['max_dc_v']},
            {'code':f"STRING_{st['string']}_MPPT_MIN",'status':'PASS' if st['vmp_hot_v']+1e-9>=inv['mppt_min_v'] else 'FAIL','observed':st['vmp_hot_v'],'limit':inv['mppt_min_v']},
            {'code':f"STRING_{st['string']}_MPPT_MAX",'status':'PASS' if st['vmp_cold_v']<=inv['mppt_max_v']+1e-9 else 'FAIL','observed':st['vmp_cold_v'],'limit':inv['mppt_max_v']},
        ])
    dc_limit_status='PASS' if dc_kwp<=inv['max_dc_kw']+1e-9 else 'FAIL'
    checks.append({'code':'INVERTER_MAX_DC_KW','status':dc_limit_status,'observed':round(dc_kwp,3),'limit':inv['max_dc_kw']})
    status='PRELIMINARY_VALIDATED_DATASHEET' if all(c['status']=='PASS' for c in checks) else 'INVALID_ELECTRICAL_LIMIT'
    return {
        'status':status,'panel_count':panel_count,'dc_kwp':round(dc_kwp,3),'dc_ac_ratio':round(dc_ac_ratio,3),
        'string_count':len(strings),'strings':strings,'mppt_string_loads':mppt_loads,'min_modules_per_string':min_series,'max_modules_per_string':max_series,'max_parallel_strings_per_mppt':max_parallel,
        'temperature_adjusted':{'temp_min_c':temp_min_c,'temp_max_c':temp_max_c,'voc_cold_v':round(voc_cold,3),'vmp_hot_v':round(vmp_hot,3),'vmp_cold_v':round(vmp_cold,3)},
        'checks':checks,
        'limitations':['Dimensionamento preliminar por limites explícitos de datasheet. Não inclui bitola/cabo, queda de tensão, proteção, aterramento, coordenação, curto-circuito, norma ABNT/NBR, exigência da distribuidora ou projeto executivo.','Nenhum fator de segurança normativo é inventado; deve ser fornecido/aplicado pelo fluxo de engenharia autorizado quando necessário.'],
    }
