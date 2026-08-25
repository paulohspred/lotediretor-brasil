from __future__ import annotations

import math
from typing import Any

from shapely.geometry import Point, mapping

ROAD_SOLVER_VERSION = 'aitec-road-engineering-v20.1'


def _circumradius(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    ab = math.dist(a, b)
    bc = math.dist(b, c)
    ca = math.dist(c, a)
    cross = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
    if min(ab, bc, ca) <= 1e-9 or cross <= 1e-9:
        return math.inf
    area = cross / 2.0
    return ab * bc * ca / (4.0 * area)


def evaluate_road_engineering(
    parcel_polygon,
    centerline,
    road_width_m: float,
    min_turn_radius_m: float,
    emergency_min_width_m: float,
    max_access_boundary_distance_m: float,
    max_grade_percent: float | None = None,
    vertex_elevations_m: list[float] | None = None,
    emergency_required: bool = False,
    emergency_turnaround_radius_m: float | None = None,
) -> dict[str, Any]:
    """Evaluate an explicit conceptual internal-road centerline against explicit constraints.

    Coordinates must already be in a metric CRS. The solver does not infer local
    fire, road, accessibility, drainage or geometric-design standards. Every
    threshold is supplied by the caller and remains visible in the result.
    """
    if parcel_polygon is None or parcel_polygon.is_empty or not parcel_polygon.is_valid:
        raise ValueError('parcel_polygon must be valid and non-empty')
    if parcel_polygon.geom_type not in ('Polygon', 'MultiPolygon'):
        raise ValueError('parcel_polygon must be Polygon/MultiPolygon')
    if centerline is None or centerline.is_empty or centerline.geom_type != 'LineString':
        raise ValueError('centerline must be a non-empty LineString')
    if len(centerline.coords) < 2:
        raise ValueError('centerline requires at least two vertices')
    if min(road_width_m, min_turn_radius_m, emergency_min_width_m) <= 0:
        raise ValueError('road width/radius/emergency width must be > 0')
    if max_access_boundary_distance_m < 0:
        raise ValueError('max_access_boundary_distance_m must be >= 0')
    if max_grade_percent is not None and max_grade_percent <= 0:
        raise ValueError('max_grade_percent must be > 0 when supplied')
    if emergency_required and (emergency_turnaround_radius_m is None or emergency_turnaround_radius_m <= 0):
        raise ValueError('emergency turnaround radius must be explicit and > 0 when emergency_required')

    coords = [(float(x), float(y)) for x, y, *_ in centerline.coords]
    surface = centerline.buffer(road_width_m / 2.0, cap_style=2, join_style=2)
    inside = parcel_polygon.covers(surface)
    start = Point(coords[0])
    access_distance = float(start.distance(parcel_polygon.boundary))

    turn_records = []
    for index in range(1, len(coords) - 1):
        radius = _circumradius(coords[index - 1], coords[index], coords[index + 1])
        turn_records.append({
            'vertex': index,
            'radius_m': None if math.isinf(radius) else round(radius, 6),
            'status': 'PASS' if radius + 1e-9 >= min_turn_radius_m else 'FAIL',
        })
    minimum_radius = min((math.inf if item['radius_m'] is None else item['radius_m'] for item in turn_records), default=math.inf)

    grade_records = []
    grade_data_status = 'NOT_REQUIRED' if max_grade_percent is None else 'PASS'
    if max_grade_percent is not None:
        if vertex_elevations_m is None or len(vertex_elevations_m) != len(coords):
            grade_data_status = 'FAIL'
        else:
            elevations = [float(value) for value in vertex_elevations_m]
            for index in range(len(coords) - 1):
                horizontal = math.dist(coords[index], coords[index + 1])
                if horizontal <= 1e-9:
                    grade = math.inf
                else:
                    grade = abs(elevations[index + 1] - elevations[index]) / horizontal * 100.0
                grade_records.append({
                    'segment': index + 1,
                    'grade_percent': None if math.isinf(grade) else round(grade, 6),
                    'status': 'PASS' if grade <= max_grade_percent + 1e-9 else 'FAIL',
                })

    turnaround = None
    turnaround_inside = None
    if emergency_required:
        turnaround = Point(coords[-1]).buffer(float(emergency_turnaround_radius_m), resolution=16)
        turnaround_inside = parcel_polygon.covers(turnaround)

    hard_results = [
        {'code': 'ROAD_SURFACE_INSIDE_PARCEL', 'status': 'PASS' if inside else 'FAIL'},
        {
            'code': 'ACCESS_AT_BOUNDARY',
            'status': 'PASS' if access_distance <= max_access_boundary_distance_m + 1e-9 else 'FAIL',
            'observed_m': round(access_distance, 6),
            'maximum_m': float(max_access_boundary_distance_m),
        },
        {
            'code': 'ROAD_MIN_TURN_RADIUS',
            'status': 'PASS' if minimum_radius + 1e-9 >= min_turn_radius_m else 'FAIL',
            'observed_minimum_m': None if math.isinf(minimum_radius) else round(minimum_radius, 6),
            'minimum_m': float(min_turn_radius_m),
        },
    ]
    if max_grade_percent is not None:
        hard_results.append({'code': 'ROAD_GRADE_DATA', 'status': grade_data_status})
        hard_results.append({
            'code': 'ROAD_MAX_GRADE',
            'status': 'PASS' if grade_data_status == 'PASS' and all(item['status'] == 'PASS' for item in grade_records) else 'FAIL',
            'maximum_percent': float(max_grade_percent),
        })
    if emergency_required:
        hard_results.extend([
            {
                'code': 'EMERGENCY_MIN_WIDTH',
                'status': 'PASS' if road_width_m + 1e-9 >= emergency_min_width_m else 'FAIL',
                'observed_m': float(road_width_m),
                'minimum_m': float(emergency_min_width_m),
            },
            {
                'code': 'EMERGENCY_TURNAROUND_INSIDE_PARCEL',
                'status': 'PASS' if turnaround_inside else 'FAIL',
                'radius_m': float(emergency_turnaround_radius_m),
            },
        ])

    failures = [item for item in hard_results if item['status'] == 'FAIL']
    return {
        'status': 'PASS' if not failures else 'SHORTFALL',
        'solver_version': ROAD_SOLVER_VERSION,
        'centerline_length_m': round(float(centerline.length), 3),
        'road_width_m': float(road_width_m),
        'surface_geometry': mapping(surface),
        'centerline_geometry': mapping(centerline),
        'turns': turn_records,
        'grades': grade_records,
        'access_boundary_distance_m': round(access_distance, 6),
        'emergency': {
            'required': bool(emergency_required),
            'minimum_width_m': float(emergency_min_width_m),
            'turnaround_radius_m': None if emergency_turnaround_radius_m is None else float(emergency_turnaround_radius_m),
            'turnaround_geometry': None if turnaround is None else mapping(turnaround),
        },
        'hard_results': hard_results,
        'limitations': [
            'Validação geométrica conceitual sobre centerline explícita; não gera projeto viário executivo.',
            'Limites de largura, raio, greide e emergência são entradas explícitas; nenhuma norma local é inferida.',
            'Não verifica swept-path de veículo específico, superelevação, drenagem, pavimento, sinalização ou aprovação do Corpo de Bombeiros.',
        ],
    }
