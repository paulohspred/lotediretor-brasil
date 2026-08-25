from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, Point, box, mapping
from shapely.ops import unary_union

BASEMENT_PARKING_VERSION = 'aitec-basement-parking-v20.1'


def _column_grid(
    garage,
    spacing_x_m: float,
    spacing_y_m: float,
    column_width_m: float,
    column_depth_m: float,
    edge_clearance_m: float,
) -> list:
    if min(spacing_x_m, spacing_y_m, column_width_m, column_depth_m) <= 0:
        raise ValueError('column grid dimensions must be > 0')
    if edge_clearance_m < 0:
        raise ValueError('column edge clearance must be >= 0')
    minx, miny, maxx, maxy = garage.bounds
    out = []
    y = miny + edge_clearance_m + spacing_y_m / 2.0
    while y <= maxy - edge_clearance_m + 1e-9:
        x = minx + edge_clearance_m + spacing_x_m / 2.0
        while x <= maxx - edge_clearance_m + 1e-9:
            col = box(
                x - column_width_m / 2.0,
                y - column_depth_m / 2.0,
                x + column_width_m / 2.0,
                y + column_depth_m / 2.0,
            )
            if garage.covers(col):
                out.append(col)
            x += spacing_x_m
        y += spacing_y_m
    return out


def _ramp_geometry(garage, ramp_centerline, ramp_width_m: float, level_depth_m: float, max_slope_percent: float):
    if ramp_centerline is None:
        return {
            'status': 'NOT_PROVIDED',
            'geometry': None,
            'length_m': None,
            'slope_percent': None,
            'hard_results': [{'code': 'RAMP_REQUIRED', 'status': 'FAIL'}],
        }
    if getattr(ramp_centerline, 'geom_type', None) != 'LineString' or ramp_centerline.is_empty:
        raise ValueError('ramp_centerline must be a non-empty LineString')
    if ramp_width_m <= 0 or level_depth_m <= 0 or max_slope_percent <= 0:
        raise ValueError('ramp width/depth/max slope must be > 0')
    length = float(ramp_centerline.length)
    if length <= 0:
        raise ValueError('ramp centerline length must be > 0')
    ramp = ramp_centerline.buffer(ramp_width_m / 2.0, cap_style=2, join_style=2)
    slope = level_depth_m / length * 100.0
    inside = garage.covers(ramp)
    return {
        'status': 'PASS' if inside and slope <= max_slope_percent + 1e-9 else 'FAIL',
        'geometry': ramp,
        'length_m': round(length, 3),
        'slope_percent': round(slope, 6),
        'hard_results': [
            {'code': 'RAMP_INSIDE_GARAGE', 'status': 'PASS' if inside else 'FAIL'},
            {
                'code': 'RAMP_MAX_SLOPE',
                'status': 'PASS' if slope <= max_slope_percent + 1e-9 else 'FAIL',
                'observed': round(slope, 6),
                'maximum': float(max_slope_percent),
            },
        ],
    }


def _stall_specs(
    required_spaces: int,
    accessible_spaces: int,
    ev_spaces: int,
    stall_width_m: float,
    stall_length_m: float,
    accessible_width_m: float,
) -> list[dict]:
    if required_spaces < 0 or accessible_spaces < 0 or ev_spaces < 0:
        raise ValueError('parking counts must be >= 0')
    if accessible_spaces > required_spaces or ev_spaces > required_spaces:
        raise ValueError('accessible/EV counts cannot exceed required spaces')
    if min(stall_width_m, stall_length_m, accessible_width_m) <= 0:
        raise ValueError('stall dimensions must be > 0')
    specs = []
    # A stall may satisfy both EV and accessible requirements only when both
    # explicit quotas still need fulfillment; the overlap is reported.
    overlap = min(accessible_spaces, ev_spaces)
    for _ in range(overlap):
        specs.append({'kind': 'ACCESSIBLE_EV', 'width_m': accessible_width_m, 'length_m': stall_length_m})
    for _ in range(accessible_spaces - overlap):
        specs.append({'kind': 'ACCESSIBLE', 'width_m': accessible_width_m, 'length_m': stall_length_m})
    for _ in range(ev_spaces - overlap):
        specs.append({'kind': 'EV', 'width_m': stall_width_m, 'length_m': stall_length_m})
    while len(specs) < required_spaces:
        specs.append({'kind': 'STANDARD', 'width_m': stall_width_m, 'length_m': stall_length_m})
    return specs


def solve_basement_parking(
    garage_polygon,
    required_spaces: int,
    accessible_spaces: int,
    ev_spaces: int,
    ramp_centerline,
    level_depth_m: float,
    max_ramp_slope_percent: float,
    ramp_width_m: float = 5.5,
    stall_width_m: float = 2.5,
    stall_length_m: float = 5.0,
    accessible_width_m: float = 3.5,
    aisle_width_m: float = 6.0,
    column_spacing_x_m: float = 7.5,
    column_spacing_y_m: float = 7.5,
    column_width_m: float = 0.4,
    column_depth_m: float = 0.4,
    column_edge_clearance_m: float = 1.0,
    fixed_exclusions: list | None = None,
    max_generated_spaces: int = 5000,
) -> dict[str, Any]:
    """Generate a deterministic conceptual single-level basement layout.

    Every statutory-looking quantity is explicit input. This solver does not
    infer local parking, PCD, EV, ramp, fire or structural requirements.
    """
    if garage_polygon is None or garage_polygon.is_empty or not garage_polygon.is_valid:
        raise ValueError('garage_polygon must be a valid non-empty polygon')
    if garage_polygon.geom_type not in ('Polygon', 'MultiPolygon'):
        raise ValueError('garage_polygon must be Polygon/MultiPolygon')
    if aisle_width_m <= 0:
        raise ValueError('aisle_width_m must be > 0')

    ramp = _ramp_geometry(
        garage_polygon,
        ramp_centerline,
        ramp_width_m,
        level_depth_m,
        max_ramp_slope_percent,
    )
    columns = _column_grid(
        garage_polygon,
        column_spacing_x_m,
        column_spacing_y_m,
        column_width_m,
        column_depth_m,
        column_edge_clearance_m,
    )
    exclusions = [g for g in (fixed_exclusions or []) if g is not None and not g.is_empty]
    if ramp['geometry'] is not None:
        exclusions.append(ramp['geometry'])
    exclusion_union = unary_union(exclusions) if exclusions else None
    free = garage_polygon.difference(exclusion_union) if exclusion_union is not None else garage_polygon.buffer(0)

    specs = _stall_specs(
        int(required_spaces),
        int(accessible_spaces),
        int(ev_spaces),
        float(stall_width_m),
        float(stall_length_m),
        float(accessible_width_m),
    )[: max(0, int(max_generated_spaces))]

    # Columns are not subtracted from the whole garage because drive aisles can
    # contain structural columns in real designs; instead, a stall is rejected
    # when its footprint collides with a column. This is a conservative stall-fit
    # rule, not structural design.
    column_union = unary_union(columns) if columns else None
    minx, miny, maxx, maxy = free.bounds if not free.is_empty else garage_polygon.bounds
    module_depth = stall_length_m * 2.0 + aisle_width_m
    phases = (0.0, stall_width_m / 2.0)
    angles = (0.0, 90.0)

    from shapely.affinity import rotate

    best = None
    origin = garage_polygon.centroid
    for angle in angles:
        rfree = rotate(free, -angle, origin=origin, use_radians=False)
        rcolumns = rotate(column_union, -angle, origin=origin, use_radians=False) if column_union is not None else None
        rminx, rminy, rmaxx, rmaxy = rfree.bounds
        for phase in phases:
            placed = []
            aisles = []
            spec_index = 0
            y = rminy
            while y + module_depth <= rmaxy + 1e-9 and spec_index < len(specs):
                x = rminx + phase
                while x < rmaxx - 1e-9 and spec_index < len(specs):
                    spec = specs[spec_index]
                    width = float(spec['width_m'])
                    if x + width > rmaxx + 1e-9:
                        break
                    aisle = box(x, y + stall_length_m, x + width, y + stall_length_m + aisle_width_m)
                    lower = box(x, y, x + width, y + stall_length_m)
                    upper = box(x, y + stall_length_m + aisle_width_m, x + width, y + module_depth)
                    chosen = None
                    for candidate in (lower, upper):
                        if not rfree.covers(candidate) or not rfree.covers(aisle):
                            continue
                        if rcolumns is not None and candidate.intersects(rcolumns):
                            continue
                        chosen = candidate
                        break
                    if chosen is not None:
                        placed.append({**spec, 'geometry': chosen})
                        aisles.append(aisle)
                        spec_index += 1
                    x += max(width, stall_width_m)
                y += module_depth
            score = (len(placed), -sum(float(item['geometry'].area) for item in placed))
            if best is None or score > best[0]:
                best = (score, angle, placed, aisles)
            if len(placed) >= len(specs):
                break
        if best and len(best[2]) >= len(specs):
            break

    _, angle, placed, aisle_cells = best if best is not None else ((0, 0), 0.0, [], [])
    final_stalls = []
    for index, item in enumerate(placed, start=1):
        geom = rotate(item['geometry'], angle, origin=origin, use_radians=False)
        final_stalls.append({
            'id': f'B1-S{index:04d}',
            'kind': item['kind'],
            'width_m': float(item['width_m']),
            'length_m': float(item['length_m']),
            'geometry': mapping(geom),
        })
    aisle_geometries = [rotate(g, angle, origin=origin, use_radians=False) for g in aisle_cells]
    aisle_union = unary_union(aisle_geometries) if aisle_geometries else None

    generated = len(final_stalls)
    kind_counts = {
        'STANDARD': sum(1 for item in final_stalls if item['kind'] == 'STANDARD'),
        'EV': sum(1 for item in final_stalls if item['kind'] in ('EV', 'ACCESSIBLE_EV')),
        'ACCESSIBLE': sum(1 for item in final_stalls if item['kind'] in ('ACCESSIBLE', 'ACCESSIBLE_EV')),
        'ACCESSIBLE_EV': sum(1 for item in final_stalls if item['kind'] == 'ACCESSIBLE_EV'),
    }
    hard_results = list(ramp['hard_results'])
    hard_results.extend([
        {
            'code': 'PARKING_TOTAL_MIN',
            'status': 'PASS' if generated >= required_spaces else 'FAIL',
            'observed': generated,
            'minimum': int(required_spaces),
        },
        {
            'code': 'PARKING_ACCESSIBLE_MIN',
            'status': 'PASS' if kind_counts['ACCESSIBLE'] >= accessible_spaces else 'FAIL',
            'observed': kind_counts['ACCESSIBLE'],
            'minimum': int(accessible_spaces),
        },
        {
            'code': 'PARKING_EV_MIN',
            'status': 'PASS' if kind_counts['EV'] >= ev_spaces else 'FAIL',
            'observed': kind_counts['EV'],
            'minimum': int(ev_spaces),
        },
    ])
    failed = [item for item in hard_results if item['status'] == 'FAIL']
    return {
        'status': 'PASS' if not failed else 'SHORTFALL',
        'solver_version': BASEMENT_PARKING_VERSION,
        'garage_area_m2': round(float(garage_polygon.area), 3),
        'required_spaces': int(required_spaces),
        'generated_spaces': generated,
        'shortfall': max(0, int(required_spaces) - generated),
        'accessible_required': int(accessible_spaces),
        'accessible_generated': kind_counts['ACCESSIBLE'],
        'ev_required': int(ev_spaces),
        'ev_generated': kind_counts['EV'],
        'accessible_ev_overlap': kind_counts['ACCESSIBLE_EV'],
        'orientation_deg': float(angle),
        'ramp': {
            'status': ramp['status'],
            'length_m': ramp['length_m'],
            'slope_percent': ramp['slope_percent'],
            'geometry': None if ramp['geometry'] is None else mapping(ramp['geometry']),
        },
        'columns': [mapping(g) for g in columns],
        'column_count': len(columns),
        'stalls': final_stalls,
        'aisle_geometry': None if aisle_union is None or aisle_union.is_empty else mapping(aisle_union),
        'hard_results': hard_results,
        'limitations': [
            'Layout conceitual de um único nível de subsolo; não dimensiona estrutura, contenção, fundação, drenagem ou ventilação.',
            'Contagens de vagas PCD/EV, dimensões e limite de rampa são entradas explícitas; nenhuma legislação local é inferida.',
            'Pilares seguem grade geométrica explícita e não constituem projeto estrutural.',
            'A circulação não verifica manobra por swept-path, raio de giro, incêndio, sinalização ou aprovação profissional.',
        ],
    }
