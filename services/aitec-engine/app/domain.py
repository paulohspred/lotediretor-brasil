from __future__ import annotations


def parking_area(required_spaces:int,stall_width_m:float=2.5,stall_length_m:float=5.0,circulation_factor:float=1.65):
    if required_spaces<0 or min(stall_width_m,stall_length_m,circulation_factor)<=0:
        raise ValueError('invalid parking input')
    stall=stall_width_m*stall_length_m
    gross=stall*circulation_factor
    return {
        'stall_area_m2':stall,
        'gross_area_per_space_m2':gross,
        'estimated_total_area_m2':gross*required_spaces,
    }


def massing_capacity(parcel_area_m2:float,buildable_area_m2:float,ca_max:float,height_max_m:float|None,floor_height_m:float=3.0,efficiency:float=0.78):
    if parcel_area_m2<=0 or buildable_area_m2<=0 or ca_max<0 or floor_height_m<=0 or not 0<efficiency<=1:
        raise ValueError('invalid massing input')
    ca_floor_area=parcel_area_m2*ca_max
    if height_max_m is None:
        floor_count=None
        height_floor_area=None
    else:
        floor_count=max(1,int(height_max_m//floor_height_m))
        height_floor_area=buildable_area_m2*floor_count
    gross=min(ca_floor_area,height_floor_area) if height_floor_area is not None else ca_floor_area
    return {
        'max_gross_floor_area_m2':gross,
        'estimated_net_area_m2':gross*efficiency,
        'estimated_floor_count':floor_count,
        'ca_limited_area_m2':ca_floor_area,
        'height_limited_area_m2':height_floor_area,
    }


def rank_scenarios(scenarios:list[dict],weights:dict[str,float]):
    valid=[s for s in scenarios if not s.get('hard_invalid')]
    if not valid:
        return []
    metrics=list(weights)
    ranges={}
    for m in metrics:
        values=[float((s.get('metrics') or {}).get(m,0)) for s in valid]
        ranges[m]=(min(values),max(values))
    ranked=[]
    for s in valid:
        score=0.0
        components={}
        for m,w in weights.items():
            value=float((s.get('metrics') or {}).get(m,0))
            lo,hi=ranges[m]
            normalized=1.0 if hi==lo else (value-lo)/(hi-lo)
            components[m]=normalized
            score+=normalized*float(w)
        ranked.append({'scenario_id':s.get('id'),'score':score,'components':components,'metrics':s.get('metrics') or {}})
    return sorted(ranked,key=lambda x:x['score'],reverse=True)


def validate_hard_constraints(metrics:dict,constraints:list[dict]):
    """Evaluate explicit numeric hard constraints conservatively.

    Unknown metrics/operators are UNEVALUATED. A scenario is PASS only when every
    supplied hard constraint is evaluable and passes.
    """
    if not constraints:
        return {
            'status':'UNVERIFIED','passed':0,'failed':0,'unevaluated':0,'results':[],
            'reason':'no_hard_constraints_supplied',
        }
    results=[]
    for item in constraints:
        code=str(item.get('code') or item.get('metric') or 'constraint')
        metric=str(item.get('metric') or '')
        raw=metrics.get(metric)
        if raw is None or isinstance(raw,bool):
            results.append({'code':code,'metric':metric,'status':'UNEVALUATED','reason':'metric_missing'})
            continue
        try:
            actual=float(raw)
        except Exception:
            results.append({'code':code,'metric':metric,'status':'UNEVALUATED','reason':'metric_not_numeric','observed':raw})
            continue
        op=str(item.get('operator') or '').strip().upper()
        tol=max(0.0,float(item.get('tolerance') or 0.0))
        value=item.get('value')
        minv=item.get('min_value')
        maxv=item.get('max_value')
        passed=None
        expected={}
        if op in ('<=','LE','LTE') and value is not None:
            passed=actual<=float(value)+tol;expected={'max':value}
        elif op in ('<','LT') and value is not None:
            passed=actual<float(value)+tol;expected={'lt':value}
        elif op in ('>=','GE','GTE') and value is not None:
            passed=actual+tol>=float(value);expected={'min':value}
        elif op in ('>','GT') and value is not None:
            passed=actual+tol>float(value);expected={'gt':value}
        elif op in ('=','==','EQ') and value is not None:
            passed=abs(actual-float(value))<=tol;expected={'eq':value,'tolerance':tol}
        elif op in ('BETWEEN','RANGE') and minv is not None and maxv is not None:
            passed=float(minv)-tol<=actual<=float(maxv)+tol;expected={'min':minv,'max':maxv}
        else:
            results.append({
                'code':code,'metric':metric,'status':'UNEVALUATED',
                'reason':'unsupported_or_incomplete_operator','operator':item.get('operator'),'observed':actual,
            })
            continue
        results.append({
            'code':code,'metric':metric,'status':'PASS' if passed else 'FAIL',
            'operator':op,'observed':actual,'expected':expected,
        })
    failed=sum(1 for r in results if r['status']=='FAIL')
    unevaluated=sum(1 for r in results if r['status']=='UNEVALUATED')
    passed=sum(1 for r in results if r['status']=='PASS')
    status='FAIL' if failed else ('UNVERIFIED' if unevaluated else 'PASS')
    return {
        'status':status,'passed':passed,'failed':failed,'unevaluated':unevaluated,'results':results,
        'policy':'A scenario is hard-valid only when every supplied hard constraint is evaluated and PASS.',
    }


def pareto_frontier(items:list[dict],objectives:dict[str,str]):
    """Return non-dominated hard-valid solutions.

    objective direction is MAX or MIN. Missing/non-numeric values make an item
    ineligible for the frontier rather than silently substituting zero.
    """
    eligible=[]
    for item in items:
        if item.get('hard_invalid'):
            continue
        metrics=item.get('metrics') or {}
        values={}
        ok=True
        for code,direction in objectives.items():
            try:
                values[code]=float(metrics[code])
            except Exception:
                ok=False;break
            if str(direction).upper() not in ('MAX','MIN'):
                raise ValueError(f'invalid objective direction:{code}:{direction}')
        if ok:
            eligible.append((item,values))
    frontier=[]
    for i,(item,vals) in enumerate(eligible):
        dominated=False
        for j,(other,ovals) in enumerate(eligible):
            if i==j:
                continue
            weak=True
            strict=False
            for code,direction in objectives.items():
                if str(direction).upper()=='MAX':
                    if ovals[code]<vals[code]:weak=False;break
                    if ovals[code]>vals[code]:strict=True
                else:
                    if ovals[code]>vals[code]:weak=False;break
                    if ovals[code]<vals[code]:strict=True
            if weak and strict:
                dominated=True;break
        if not dominated:
            frontier.append(item)
    return frontier


def generate_surface_parking_layout(
    legal_area,
    building_footprints:list,
    required_spaces:int,
    stall_width_m:float=2.5,
    stall_length_m:float=5.0,
    aisle_width_m:float=6.0,
    building_clearance_m:float=1.0,
    max_generated_spaces:int=5000,
):
    """Generate a deterministic conceptual surface-parking layout.

    The solver uses double-loaded parking modules (stall + aisle + stall) and
    searches a small set of orientations. Every stall and aisle cell must be
    contained in the free legal area. This is deliberately a *surface* parking
    solver: no ramps, structural columns, basement geometry or local statutory
    dimensions are inferred.
    """
    import math
    from shapely.geometry import box
    from shapely.affinity import rotate
    from shapely.ops import unary_union

    if required_spaces<0:
        raise ValueError('required_spaces must be >= 0')
    if min(stall_width_m,stall_length_m,aisle_width_m)<=0:
        raise ValueError('invalid parking dimensions')
    if legal_area is None or legal_area.is_empty or not legal_area.is_valid:
        raise ValueError('invalid parking legal area')
    if required_spaces==0:
        return {
            'status':'NOT_REQUIRED','required_spaces':0,'generated_spaces':0,'shortfall':0,
            'stalls':[],'aisles':[],'impervious_area_m2':0.0,'stall_area_m2':0.0,'aisle_area_m2':0.0,
            'orientation_deg':0.0,'capacity_capped':False,
        }

    exclusions=[]
    for fp in building_footprints:
        if fp is not None and not fp.is_empty:
            exclusions.append(fp.buffer(max(0.0,building_clearance_m),join_style=2))
    free=legal_area.difference(unary_union(exclusions) if exclusions else legal_area.buffer(0)) if exclusions else legal_area.buffer(0)
    if free.is_empty:
        return {
            'status':'NO_SPACE','required_spaces':required_spaces,'generated_spaces':0,'shortfall':required_spaces,
            'stalls':[],'aisles':[],'impervious_area_m2':0.0,'stall_area_m2':0.0,'aisle_area_m2':0.0,
            'orientation_deg':None,'capacity_capped':required_spaces>max_generated_spaces,
        }

    target=min(int(required_spaces),int(max_generated_spaces))
    origin=free.centroid
    module_depth=stall_length_m*2+aisle_width_m
    angles=(0.0,90.0,45.0,135.0,30.0,60.0,120.0,150.0)
    best=None

    for angle in angles:
        rfree=rotate(free,-angle,origin=origin,use_radians=False)
        minx,miny,maxx,maxy=rfree.bounds
        if maxx-minx<stall_width_m or maxy-miny<stall_length_m:
            continue
        stalls=[]
        aisle_cells=[]
        # Try several deterministic phase offsets so narrow/irregular parcels are
        # less sensitive to where the grid starts.
        phases=(0.0,stall_width_m/2)
        for phase in phases:
            p_stalls=[]
            p_aisles=[]
            y=miny
            row_index=0
            while y+module_depth<=maxy+1e-9 and len(p_stalls)<target:
                x=minx+phase
                while x+stall_width_m<=maxx+1e-9 and len(p_stalls)<target:
                    lower=box(x,y,x+stall_width_m,y+stall_length_m)
                    aisle=box(x,y+stall_length_m,x+stall_width_m,y+stall_length_m+aisle_width_m)
                    upper=box(x,y+stall_length_m+aisle_width_m,x+stall_width_m,y+module_depth)
                    # A stall is only admitted with its adjacent drive-aisle cell.
                    if rfree.covers(aisle):
                        if rfree.covers(lower):
                            p_stalls.append(lower);p_aisles.append(aisle)
                        if len(p_stalls)<target and rfree.covers(upper):
                            p_stalls.append(upper);p_aisles.append(aisle)
                    x+=stall_width_m
                y+=module_depth
                row_index+=1
                if row_index>10000:
                    break
            if len(p_stalls)>len(stalls):
                stalls,aisle_cells=p_stalls,p_aisles
            if len(stalls)>=target:
                break

        if stalls:
            stalls=[rotate(g,angle,origin=origin,use_radians=False) for g in stalls[:target]]
            aisle_cells=[rotate(g,angle,origin=origin,use_radians=False) for g in aisle_cells[:len(stalls)]]
            aisle_union=unary_union(aisle_cells) if aisle_cells else None
            stall_union=unary_union(stalls)
            stall_area=float(stall_union.area)
            aisle_area=float(aisle_union.area) if aisle_union is not None and not aisle_union.is_empty else 0.0
            candidate={
                'orientation_deg':angle,
                'stalls':stalls,
                'aisles':([] if aisle_union is None or aisle_union.is_empty else [aisle_union]),
                'generated_spaces':len(stalls),
                'stall_area_m2':stall_area,
                'aisle_area_m2':aisle_area,
                'impervious_area_m2':stall_area+aisle_area,
            }
            if best is None or candidate['generated_spaces']>best['generated_spaces'] or (
                candidate['generated_spaces']==best['generated_spaces'] and candidate['impervious_area_m2']<best['impervious_area_m2']
            ):
                best=candidate
        if best and best['generated_spaces']>=target:
            break

    if best is None:
        best={'orientation_deg':None,'stalls':[],'aisles':[],'generated_spaces':0,'stall_area_m2':0.0,'aisle_area_m2':0.0,'impervious_area_m2':0.0}
    generated=int(best['generated_spaces'])
    shortfall=max(0,int(required_spaces)-generated)
    return {
        'status':'PASS' if shortfall==0 else 'SHORTFALL',
        'required_spaces':int(required_spaces),
        'generated_spaces':generated,
        'shortfall':shortfall,
        'stalls':best['stalls'],
        'aisles':best['aisles'],
        'stall_area_m2':round(float(best['stall_area_m2']),2),
        'aisle_area_m2':round(float(best['aisle_area_m2']),2),
        'impervious_area_m2':round(float(best['impervious_area_m2']),2),
        'orientation_deg':best['orientation_deg'],
        'capacity_capped':int(required_spaces)>int(max_generated_spaces),
        'dimensions':{
            'stall_width_m':stall_width_m,'stall_length_m':stall_length_m,
            'aisle_width_m':aisle_width_m,'building_clearance_m':building_clearance_m,
        },
    }



def generate_access_road_layout(
    parcel_geometry,
    building_footprints:list,
    parking_aisles:list|None,
    access_point,
    road_width_m:float=6.0,
    boundary_tolerance_m:float=12.0,
):
    """Generate a deterministic conceptual internal access road.

    An access point must be explicit. The function never invents a street or
    entrance. It snaps the supplied point to the parcel boundary when it is
    within the configured tolerance, tries direct and orthogonal dog-leg routes,
    and rejects routes that collide with building footprints.
    """
    from shapely.geometry import LineString, Point
    from shapely.ops import nearest_points, unary_union
    if access_point is None:
        return {'status':'NOT_PROVIDED','connected':False,'road':None,'centerline':None,'length_m':0.0,'area_m2':0.0}
    if parcel_geometry is None or parcel_geometry.is_empty or not parcel_geometry.is_valid:
        raise ValueError('invalid parcel geometry')
    if getattr(access_point,'geom_type',None)!='Point' or access_point.is_empty:
        raise ValueError('access_point must be a Point')
    if road_width_m<=0:
        raise ValueError('road_width_m must be > 0')
    boundary_point=nearest_points(parcel_geometry.boundary,access_point)[0]
    boundary_distance=float(access_point.distance(parcel_geometry.boundary))
    if boundary_distance>boundary_tolerance_m:
        return {'status':'INVALID_ACCESS_POINT','connected':False,'reason':'access_point_not_near_boundary','boundary_distance_m':round(boundary_distance,3),'road':None,'centerline':None,'length_m':0.0,'area_m2':0.0}
    obstacles=unary_union([g for g in building_footprints if g is not None and not g.is_empty]) if building_footprints else None
    targets=[]
    for a in parking_aisles or []:
        if a is not None and not a.is_empty:
            targets.append(a.centroid)
    if targets:
        target=min(targets,key=lambda pt:pt.distance(boundary_point))
    elif obstacles is not None and not obstacles.is_empty:
        target=obstacles.centroid
    else:
        target=parcel_geometry.representative_point()
    dx,dy=target.x-boundary_point.x,target.y-boundary_point.y
    norm=(dx*dx+dy*dy)**0.5
    if norm<1e-9:
        return {'status':'INVALID_TARGET','connected':False,'reason':'access_target_coincident','road':None,'centerline':None,'length_m':0.0,'area_m2':0.0}
    inset=min(max(road_width_m/2,0.5),max(norm*.25,0.5))
    start=Point(boundary_point.x+dx/norm*inset,boundary_point.y+dy/norm*inset)
    candidates=[
        LineString([start,target]),
        LineString([start,(target.x,start.y),target]),
        LineString([start,(start.x,target.y),target]),
    ]
    rp=parcel_geometry.representative_point()
    candidates.extend([LineString([start,rp,target])])
    best=None
    for line in candidates:
        if line.is_empty or line.length<=0: continue
        road=line.buffer(road_width_m/2,cap_style=2,join_style=2)
        clipped=road.intersection(parcel_geometry)
        if clipped.is_empty: continue
        if obstacles is not None and not obstacles.is_empty and clipped.intersection(obstacles).area>1e-7:
            continue
        coverage=float(clipped.area/max(road.area,1e-9))
        # At an entrance a small clipping against the outer boundary is expected.
        if coverage<0.90: continue
        score=(float(line.length),-coverage)
        if best is None or score<best[0]:best=(score,line,clipped,coverage)
    if best is None:
        return {'status':'NO_ROUTE','connected':False,'reason':'no_collision_free_candidate','boundary_distance_m':round(boundary_distance,3),'road':None,'centerline':None,'length_m':0.0,'area_m2':0.0}
    _,line,road,coverage=best
    return {
        'status':'PASS','connected':True,'centerline':line,'road':road,
        'length_m':round(float(line.length),2),'area_m2':round(float(road.area),2),
        'road_width_m':road_width_m,'boundary_distance_m':round(boundary_distance,3),
        'coverage_ratio':round(coverage,4),
        'limitations':['Traçado conceitual; não verifica raio de giro, greide, drenagem, emergência, portaria ou norma viária local.'],
    }


def allocate_unit_mix(net_area_m2:float,unit_types:list[dict],min_total_units:int|None=None):
    """Allocate a preliminary unit mix from explicit areas/minima/target shares.

    This is a deterministic packing-by-area routine, not a floor-plan solver.
    Minimum counts and an optional minimum total are treated as hard program
    constraints; target shares are optimization preferences only.
    """
    if net_area_m2<0:raise ValueError('net_area_m2 must be >= 0')
    if not unit_types:
        return {'status':'NOT_PROVIDED','total_units':0,'used_area_m2':0.0,'unallocated_area_m2':round(net_area_m2,2),'items':[],'hard_results':[]}
    items=[]
    for i,raw in enumerate(unit_types):
        name=str(raw.get('name') or raw.get('type') or f'TYPE-{i+1}')
        area=float(raw.get('target_area_m2') or raw.get('area_m2') or 0)
        if area<=0:raise ValueError(f'unit type {name} requires positive target_area_m2')
        minimum=max(0,int(raw.get('min_count') or raw.get('minimum') or 0))
        maximum=raw.get('max_count')
        maximum=None if maximum is None else max(minimum,int(maximum))
        share=raw.get('target_share')
        share=None if share is None else max(0.0,float(share))
        items.append({'name':name,'target_area_m2':area,'min_count':minimum,'max_count':maximum,'target_share':share,'count':minimum})
    used=sum(x['count']*x['target_area_m2'] for x in items)
    hard=[]
    if used>net_area_m2+1e-9:
        hard.append({'code':'UNIT_MIX_MIN_COUNTS','status':'FAIL','observed_area_m2':round(used,2),'available_area_m2':round(net_area_m2,2)})
        return {'status':'SHORTFALL','total_units':sum(x['count'] for x in items),'used_area_m2':round(used,2),'unallocated_area_m2':round(max(0,net_area_m2-used),2),'items':items,'hard_results':hard}
    shares=[x['target_share'] for x in items]
    if not any(s is not None and s>0 for s in shares):
        for x in items:x['target_share']=1/len(items)
    else:
        total=sum(float(x['target_share'] or 0) for x in items)
        if total<=0:total=1
        for x in items:x['target_share']=float(x['target_share'] or 0)/total
    # Add one unit at a time to the type furthest below its target share. This
    # avoids hiding an optimizer behind opaque heuristics and is reproducible.
    guard=0
    while guard<100000:
        guard+=1
        candidates=[]
        for idx,x in enumerate(items):
            if x['max_count'] is not None and x['count']>=x['max_count']:continue
            if used+x['target_area_m2']>net_area_m2+1e-9:continue
            target_area=net_area_m2*float(x['target_share'])
            current=x['count']*x['target_area_m2']
            deficit=target_area-current
            candidates.append((deficit,-x['target_area_m2'],-idx,idx))
        if not candidates:break
        idx=max(candidates)[-1]
        x=items[idx];x['count']+=1;used+=x['target_area_m2']
    total_units=sum(x['count'] for x in items)
    for x in items:
        hard.append({'code':f"UNIT_MIN:{x['name']}",'status':'PASS' if x['count']>=x['min_count'] else 'FAIL','observed':x['count'],'minimum':x['min_count']})
        x['private_area_m2']=round(x['count']*x['target_area_m2'],2)
        x['achieved_share']=round((x['private_area_m2']/used) if used>0 else 0,4)
    if min_total_units is not None:
        hard.append({'code':'PROGRAM_MIN_UNITS','status':'PASS' if total_units>=int(min_total_units) else 'FAIL','observed':total_units,'minimum':int(min_total_units)})
    status='PASS' if all(x['status']=='PASS' for x in hard) else 'SHORTFALL'
    return {'status':status,'total_units':total_units,'used_area_m2':round(used,2),'unallocated_area_m2':round(max(0,net_area_m2-used),2),'items':items,'hard_results':hard,'method':'deterministic area allocation against explicit target shares/minima'}


def estimate_cut_fill_from_samples(building_footprints:list,samples:list[dict]):
    """Estimate conceptual cut/fill from explicit metric XYZ samples.

    The estimate uses a median pad elevation per building and equal-area sample
    weighting. It intentionally refuses to fabricate terrain when fewer than
    three useful samples are available near a footprint.
    """
    from statistics import median
    from shapely.geometry import Point
    if not samples:
        return {'status':'NOT_PROVIDED','cut_m3':None,'fill_m3':None,'earthwork_m3':None,'sample_count':0,'buildings':[]}
    pts=[]
    for s in samples:
        try:x=float(s['x']);y=float(s['y']);z=float(s['z'])
        except Exception:raise ValueError('terrain samples require numeric x/y/z in the site metric CRS')
        pts.append((Point(x,y),z))
    out=[];total_cut=total_fill=0.0;used_ids=set()
    for idx,fp in enumerate(building_footprints):
        if fp is None or fp.is_empty:continue
        radius=max(5.0,(float(fp.area)**0.5)*.6)
        local=[(i,p,z) for i,(p,z) in enumerate(pts) if fp.buffer(radius).covers(p)]
        if len(local)<3:
            local=sorted([(i,p,z) for i,(p,z) in enumerate(pts)],key=lambda a:a[1].distance(fp))[:min(12,len(pts))]
        if len(local)<3:
            out.append({'building':idx+1,'status':'INSUFFICIENT_DATA','sample_count':len(local)});continue
        zvals=[z for _,_,z in local];pad=float(median(zvals));weight=float(fp.area)/len(local)
        cut=sum(max(z-pad,0)*weight for _,_,z in local);fill=sum(max(pad-z,0)*weight for _,_,z in local)
        total_cut+=cut;total_fill+=fill
        for i,_,_ in local:used_ids.add(i)
        out.append({'building':idx+1,'status':'CALCULATED_PRELIMINARY','sample_count':len(local),'pad_elevation_m':round(pad,3),'cut_m3':round(cut,2),'fill_m3':round(fill,2),'earthwork_m3':round(cut+fill,2)})
    calculated=[x for x in out if x['status']=='CALCULATED_PRELIMINARY']
    if not calculated:
        return {'status':'INSUFFICIENT_DATA','cut_m3':None,'fill_m3':None,'earthwork_m3':None,'sample_count':len(used_ids),'buildings':out,'limitations':['Amostras insuficientes para estimar platôs.']}
    return {'status':'CALCULATED_PRELIMINARY','cut_m3':round(total_cut,2),'fill_m3':round(total_fill,2),'earthwork_m3':round(total_cut+total_fill,2),'sample_count':len(used_ids),'buildings':out,'method':'median pad + equal-area sample weighting','limitations':['Estimativa conceitual baseada exclusivamente nas amostras fornecidas; não substitui TIN/levantamento/topografia/terraplenagem executiva.']}


def solve_building_stack(building_footprints:list,floors:int,core_area_m2:float=40.0,circulation_width_m:float=1.8):
    """Create conceptual floor/core/circulation objects from mass footprints."""
    import math
    from shapely.geometry import Point
    if floors<1:raise ValueError('floors must be >= 1')
    if core_area_m2<=0 or circulation_width_m<=0:raise ValueError('invalid building solver dimensions')
    buildings=[];cores=[];circulations=[]
    total_core=total_circ=total_net=0.0
    for idx,fp in enumerate(building_footprints):
        if fp is None or fp.is_empty:continue
        interior=fp.buffer(-max(0.25,circulation_width_m*.25),join_style=2)
        if interior.is_empty:interior=fp
        center=interior.representative_point()
        radius=math.sqrt(core_area_m2/math.pi)
        core=center.buffer(radius,resolution=8)
        shrink=0
        while not fp.covers(core) and shrink<12:
            radius*=.82;core=center.buffer(radius,resolution=8);shrink+=1
        if not fp.covers(core) or core.area<min(4.0,core_area_m2*.15):
            buildings.append({'building':idx+1,'status':'CORE_DOES_NOT_FIT','floors':floors,'floor_plate_area_m2':round(float(fp.area),2)});continue
        circulation=core.buffer(circulation_width_m,join_style=2).intersection(fp).difference(core)
        net_per_floor=max(0.0,float(fp.area)-float(core.area)-float(circulation.area))
        cores.append(core);circulations.append(circulation)
        total_core+=float(core.area)*floors;total_circ+=float(circulation.area)*floors;total_net+=net_per_floor*floors
        buildings.append({'building':idx+1,'status':'PRELIMINARY','floors':floors,'floor_plate_area_m2':round(float(fp.area),2),'core_area_m2':round(float(core.area),2),'circulation_area_m2':round(float(circulation.area),2),'net_program_area_m2':round(net_per_floor,2),'gross_stack_area_m2':round(float(fp.area)*floors,2),'net_stack_area_m2':round(net_per_floor*floors,2)})
    status='PRELIMINARY' if buildings and all(x['status']=='PRELIMINARY' for x in buildings) else 'PARTIAL'
    return {'status':status,'buildings':buildings,'cores':cores,'circulations':circulations,'total_core_area_m2':round(total_core,2),'total_circulation_area_m2':round(total_circ,2),'total_net_program_area_m2':round(total_net,2),'limitations':['Core e circulação são envelopes conceituais; não validam incêndio, acessibilidade, elevadores, escadas, shafts, estrutura ou norma local.']}


def generate_site_solutions(
    envelope,
    parcel_area_m2:float,
    ca_max:float,
    to_max:float,
    tp_min:float,
    height_max_m:float,
    floor_height_m:float=3.0,
    efficiency:float=0.78,
    avg_unit_area_m2:float=65.0,
    min_buildings:int=1,
    max_buildings:int=4,
    min_spacing_m:float=8.0,
    spaces_per_unit:float=1.0,
    required_spaces:int|None=None,
    count:int=30,
    seed:int=1,
    stall_width_m:float=2.5,
    stall_length_m:float=5.0,
    aisle_width_m:float=6.0,
    parcel_geometry=None,
    access_point=None,
    access_required:bool=False,
    road_width_m:float=6.0,
    unit_mix:list[dict]|None=None,
    min_total_units:int|None=None,
    terrain_samples:list[dict]|None=None,
    core_area_m2:float=40.0,
    circulation_width_m:float=1.8,
    locked_footprints:list|None=None,
):
    """Deterministic geometry-aware Site Solver RC3.

    RC3 extends the RC2 massing/parking solver with explicit access-road
    geometry, lock-preserving regeneration, unit-mix hard minima, conceptual
    cut/fill from supplied XYZ samples and a preliminary building/core layer.
    """
    import math,random
    from shapely.geometry import box
    from shapely.affinity import rotate,translate
    from shapely.ops import unary_union

    if envelope is None or envelope.is_empty or not envelope.is_valid:raise ValueError('invalid envelope')
    if parcel_area_m2<=0 or ca_max<0 or not 0<=to_max<=1 or not 0<=tp_min<=1 or height_max_m<=0:raise ValueError('invalid legal limits')
    if floor_height_m<=0 or not 0<efficiency<=1 or avg_unit_area_m2<=0:raise ValueError('invalid program')
    if min_buildings<1 or max_buildings<min_buildings or max_buildings>20:raise ValueError('invalid building range')
    if min(stall_width_m,stall_length_m,aisle_width_m,road_width_m,core_area_m2,circulation_width_m)<=0:raise ValueError('invalid dimensions')
    parcel_geometry=parcel_geometry if parcel_geometry is not None else envelope
    locked=[(g if g.is_valid else g.buffer(0)) for g in (locked_footprints or []) if g is not None and not g.is_empty]
    if len(locked)>max_buildings:raise ValueError('locked footprints exceed max_buildings')
    for i,g in enumerate(locked):
        if not envelope.covers(g):raise ValueError(f'locked footprint {i+1} is outside envelope')
        for old in locked[:i]:
            if g.buffer(min_spacing_m/2).intersects(old.buffer(min_spacing_m/2)):raise ValueError('locked footprints violate min spacing')

    count=max(1,min(int(count),200));rng=random.Random(int(seed));minx,miny,maxx,maxy=envelope.bounds
    legal_footprint_cap=min(float(envelope.area),parcel_area_m2*to_max);max_floors=max(1,int(height_max_m//floor_height_m))
    solutions=[];fingerprints=set();attempts=0;max_attempts=count*120;angles=[0,15,30,45,60,75,90,105,120,135,150,165]
    locked_area=float(unary_union(locked).area) if locked else 0.0
    if locked_area>legal_footprint_cap+1e-6:return []

    while len(solutions)<count and attempts<max_attempts:
        attempts+=1
        building_count=max(len(locked),rng.randint(min_buildings,max_buildings))
        fill=rng.uniform(.30,.82);target_total=max(locked_area,legal_footprint_cap*fill)
        footprints=list(locked);angle_base=rng.choice(angles)+rng.uniform(-4.0,4.0);failed=False
        remaining_count=building_count-len(footprints);remaining_area=max(0.0,target_total-locked_area)
        for _b in range(remaining_count):
            area=max(20.0,(remaining_area/max(1,remaining_count))*rng.uniform(.82,1.18))
            aspect=rng.uniform(.55,2.1);w=math.sqrt(area*aspect);h=math.sqrt(area/aspect);placed=None
            for _ in range(300):
                cx=rng.uniform(minx,maxx);cy=rng.uniform(miny,maxy);rect=box(-w/2,-h/2,w/2,h/2)
                rect=rotate(rect,angle_base+rng.uniform(-12,12),origin=(0,0),use_radians=False);rect=translate(rect,cx,cy)
                if not envelope.covers(rect):continue
                if any(rect.buffer(min_spacing_m/2).intersects(old.buffer(min_spacing_m/2)) for old in footprints):continue
                placed=rect;break
            if placed is None:failed=True;break
            footprints.append(placed)
        if failed or not footprints:continue
        union=unary_union(footprints);footprint_area=float(union.area)
        if footprint_area<=0 or footprint_area>legal_footprint_cap+1e-6:continue
        gross_cap=min(parcel_area_m2*ca_max,footprint_area*max_floors);floors=max(1,min(max_floors,int(math.ceil(gross_cap/max(footprint_area,1e-9)))))
        gross=min(parcel_area_m2*ca_max,footprint_area*floors);net=gross*efficiency
        mix=allocate_unit_mix(net,unit_mix or [],min_total_units)
        units=mix['total_units'] if unit_mix else max(0,int(net//avg_unit_area_m2))
        spaces=int(math.ceil(required_spaces if required_spaces is not None else units*spaces_per_unit))
        parking=generate_surface_parking_layout(envelope,footprints,spaces,stall_width_m,stall_length_m,aisle_width_m,building_clearance_m=max(0.5,min_spacing_m/4 if min_spacing_m else 0.5))
        road=generate_access_road_layout(parcel_geometry,footprints,parking['aisles'],access_point,road_width_m) if access_point is not None else {'status':'NOT_PROVIDED','connected':False,'road':None,'centerline':None,'length_m':0.0,'area_m2':0.0}
        impervious_parts=[union,*parking['stalls'],*parking['aisles']]
        if road.get('road') is not None:impervious_parts.append(road['road'])
        impervious=float(unary_union(impervious_parts).area) if impervious_parts else footprint_area
        permeable=max(0.0,parcel_area_m2-impervious);tp=permeable/parcel_area_m2;to=footprint_area/parcel_area_m2;ca=gross/parcel_area_m2;height=floors*floor_height_m
        building=solve_building_stack(footprints,floors,core_area_m2,circulation_width_m)
        terrain=estimate_cut_fill_from_samples(footprints,terrain_samples or [])
        metrics={
            'footprint_area_m2':round(footprint_area,2),'buildable_envelope_area_m2':round(float(envelope.area),2),'gross_floor_area_m2':round(gross,2),'estimated_net_area_m2':round(net,2),'total_units':units,'building_count':building_count,'locked_building_count':len(locked),'floors':floors,'height_m':round(height,2),'ca_used':round(ca,6),'to_used':round(to,6),'permeable_area_m2':round(permeable,2),'tp_achieved':round(tp,6),'required_spaces':spaces,'parking_spaces_generated':parking['generated_spaces'],'parking_shortfall':parking['shortfall'],'parking_area_m2':round(float(parking['impervious_area_m2']),2),'parking_stall_area_m2':parking['stall_area_m2'],'parking_aisle_area_m2':parking['aisle_area_m2'],'surface_parking_fit':parking['shortfall']==0,'access_connected':1 if road.get('connected') else 0,'access_road_length_m':round(float(road.get('length_m') or 0),2),'access_road_area_m2':round(float(road.get('area_m2') or 0),2),'impervious_area_m2':round(impervious,2),'open_area_m2':round(max(0.0,parcel_area_m2-footprint_area),2),'unit_mix_total_units':mix['total_units'] if unit_mix else None,'unit_mix_unallocated_area_m2':mix['unallocated_area_m2'] if unit_mix else None,'earthwork_m3':terrain.get('earthwork_m3'),'cut_m3':terrain.get('cut_m3'),'fill_m3':terrain.get('fill_m3'),'building_core_area_m2':building.get('total_core_area_m2'),'building_circulation_area_m2':building.get('total_circulation_area_m2'),
        }
        checks=[{'code':'CA_MAX','metric':'ca_used','operator':'<=','value':ca_max},{'code':'TO_MAX','metric':'to_used','operator':'<=','value':to_max},{'code':'TP_MIN','metric':'tp_achieved','operator':'>=','value':tp_min},{'code':'HEIGHT_MAX','metric':'height_m','operator':'<=','value':height_max_m},{'code':'PARKING_MIN','metric':'parking_spaces_generated','operator':'>=','value':spaces}]
        if access_required or access_point is not None:checks.append({'code':'ACCESS_REQUIRED','metric':'access_connected','operator':'>=','value':1})
        if min_total_units is not None:checks.append({'code':'PROGRAM_MIN_UNITS','metric':'total_units','operator':'>=','value':int(min_total_units)})
        validation=validate_hard_constraints(metrics,checks)
        # Unit type minima are also hard constraints when a unit mix is supplied.
        if unit_mix and mix['status']!='PASS':
            for r in mix['hard_results']:
                if r['status']!='PASS':validation['results'].append({'code':r['code'],'metric':'unit_mix','status':'FAIL','observed':r.get('observed'),'expected':{'minimum':r.get('minimum')}})
            validation['failed']=sum(1 for r in validation['results'] if r['status']=='FAIL');validation['status']='FAIL'
        hard_invalid=validation['status']!='PASS'
        centroids=sorted((round(g.centroid.x,1),round(g.centroid.y,1)) for g in footprints);fp=(building_count,len(locked),round(angle_base%180,1),tuple(centroids),round(footprint_area,1),parking['generated_spaces'],round(float(road.get('length_m') or 0),1))
        if fp in fingerprints:continue
        fingerprints.add(fp)
        solutions.append({'id':f'sol-{len(solutions)+1:03d}','seed':int(seed),'variation':attempts,'angle_deg':round(angle_base%180,2),'hard_invalid':hard_invalid,'validation':validation,'metrics':metrics,'footprints':footprints,'locked_count':len(locked),'parking_stalls':parking['stalls'],'parking_aisles':parking['aisles'],'parking':{k:v for k,v in parking.items() if k not in ('stalls','aisles')},'road':road,'unit_mix':mix,'terrain':terrain,'building':building,'limitations':['Building footprints, acesso, estacionamento, core/circulação e cut/fill continuam conceituais; não são projeto executivo.','Acesso só é gerado a partir de ponto fornecido; o motor não inventa frente/rua/portaria.','Parking RC3 continua de superfície; não resolve subsolos/rampas/pilares/PCD/EV sem regras explícitas.','Unit mix RC3 aloca por área e metas; ainda não posiciona unidades no floor plate.','Cut/fill RC3 usa somente amostras XYZ explícitas e não substitui TIN/topografia.']})
    return solutions
