from __future__ import annotations

import math
from typing import Any

from shapely.geometry import box, mapping
from shapely.ops import substring, unary_union

ROOM_SOLVER_VERSION = 'aitec-room-graph-v20.1'


def _longest_line(geometry):
    if geometry is None or geometry.is_empty:
        return None
    if geometry.geom_type == 'LineString':
        return geometry
    if geometry.geom_type == 'MultiLineString':
        return max(geometry.geoms, key=lambda item: float(item.length), default=None)
    if geometry.geom_type == 'GeometryCollection':
        lines = [g for g in geometry.geoms if g.geom_type in ('LineString', 'MultiLineString')]
        candidates = []
        for item in lines:
            if item.geom_type == 'LineString':
                candidates.append(item)
            else:
                candidates.extend(item.geoms)
        return max(candidates, key=lambda item: float(item.length), default=None)
    return None


def _center_segment(line, length_m: float):
    if line is None or line.is_empty or length_m <= 0 or line.length + 1e-9 < length_m:
        return None
    start = max(0.0, (float(line.length) - length_m) / 2.0)
    end = min(float(line.length), start + length_m)
    return substring(line, start, end)


def _normalize_rooms(room_program: list[dict]) -> list[dict]:
    if not room_program:
        raise ValueError('room_program is required')
    out = []
    names = set()
    for index, raw in enumerate(room_program):
        name = str(raw.get('name') or raw.get('code') or f'ROOM-{index + 1}').strip()
        if not name or name in names:
            raise ValueError(f'invalid or duplicate room name:{name}')
        names.add(name)
        target = float(raw.get('target_area_m2') or raw.get('area_m2') or 0)
        if target <= 0:
            raise ValueError(f'room {name} requires positive target_area_m2')
        min_area = float(raw.get('min_area_m2') or 0)
        max_area_raw = raw.get('max_area_m2')
        max_area = None if max_area_raw is None else float(max_area_raw)
        min_width = float(raw.get('min_width_m') or 0)
        min_depth = float(raw.get('min_depth_m') or 0)
        if min(min_area, min_width, min_depth) < 0:
            raise ValueError(f'room {name} minima cannot be negative')
        if max_area is not None and max_area < min_area:
            raise ValueError(f'room {name} max_area_m2 cannot be below min_area_m2')
        exterior_required = bool(raw.get('exterior_opening_required', False))
        exterior_width = raw.get('exterior_opening_width_m')
        if exterior_required and (exterior_width is None or float(exterior_width) <= 0):
            raise ValueError(f'room {name} requires explicit exterior_opening_width_m')
        out.append({
            'name': name,
            'target_area_m2': target,
            'min_area_m2': min_area,
            'max_area_m2': max_area,
            'min_width_m': min_width,
            'min_depth_m': min_depth,
            'exterior_opening_required': exterior_required,
            'exterior_opening_width_m': None if exterior_width is None else float(exterior_width),
            'entry': bool(raw.get('entry', False)),
        })
    return out


def _normalize_adjacencies(adjacencies: list[dict] | None, names: set[str]) -> list[dict]:
    out = []
    seen = set()
    for raw in adjacencies or []:
        left = str(raw.get('a') or raw.get('from') or '').strip()
        right = str(raw.get('b') or raw.get('to') or '').strip()
        if left not in names or right not in names or left == right:
            raise ValueError(f'invalid adjacency:{left}:{right}')
        pair = tuple(sorted((left, right)))
        if pair in seen:
            raise ValueError(f'duplicate adjacency:{pair[0]}:{pair[1]}')
        seen.add(pair)
        required = bool(raw.get('required', True))
        opening_required = bool(raw.get('opening_required', required))
        opening_width = raw.get('opening_width_m')
        if opening_required and (opening_width is None or float(opening_width) <= 0):
            raise ValueError(f'adjacency {left}:{right} requires explicit opening_width_m')
        out.append({
            'a': left,
            'b': right,
            'required': required,
            'min_shared_boundary_m': max(0.0, float(raw.get('min_shared_boundary_m') or 0)),
            'opening_required': opening_required,
            'opening_width_m': None if opening_width is None else float(opening_width),
        })
    return out


def _room_order(rooms: list[dict], adjacencies: list[dict]) -> list[str]:
    names = [item['name'] for item in rooms]
    degree = {name: 0 for name in names}
    linked = {name: set() for name in names}
    for rule in adjacencies:
        degree[rule['a']] += 1
        degree[rule['b']] += 1
        linked[rule['a']].add(rule['b'])
        linked[rule['b']].add(rule['a'])
    entries = [item['name'] for item in rooms if item['entry']]
    current = min(entries) if entries else max(names, key=lambda name: (degree[name], name))
    order = [current]
    remaining = set(names) - {current}
    while remaining:
        candidates = sorted(
            remaining,
            key=lambda name: (
                1 if name in linked[current] else 0,
                sum(1 for prior in order if name in linked[prior]),
                degree[name],
                name,
            ),
            reverse=True,
        )
        current = candidates[0]
        order.append(current)
        remaining.remove(current)
    return order


def _partition(unit_polygon, rooms_by_name: dict[str, dict], order: list[str], axis: str):
    minx, miny, maxx, maxy = unit_polygon.bounds
    targets = [rooms_by_name[name]['target_area_m2'] for name in order]
    target_sum = sum(targets)
    if target_sum <= 0:
        raise ValueError('target area sum must be > 0')
    span = (maxx - minx) if axis == 'x' else (maxy - miny)
    cursor = minx if axis == 'x' else miny
    results = {}
    for index, name in enumerate(order):
        if index == len(order) - 1:
            stop = maxx if axis == 'x' else maxy
        else:
            fraction = targets[index] / target_sum
            stop = cursor + span * fraction
        cutter = box(cursor, miny - span * 2, stop, maxy + span * 2) if axis == 'x' else box(minx - span * 2, cursor, maxx + span * 2, stop)
        geom = unit_polygon.intersection(cutter)
        results[name] = geom
        cursor = stop
    return results


def _evaluate(unit_polygon, rooms: list[dict], adjacencies: list[dict], geometries: dict[str, Any], axis: str):
    hard = []
    room_results = []
    openings = []
    graph_edges = []
    by_name = {item['name']: item for item in rooms}

    for name in sorted(geometries):
        spec = by_name[name]
        geom = geometries[name]
        area = float(geom.area) if geom is not None and not geom.is_empty else 0.0
        if geom is None or geom.is_empty:
            width = depth = 0.0
        else:
            minx, miny, maxx, maxy = geom.bounds
            sides = sorted((maxx - minx, maxy - miny))
            width, depth = float(sides[0]), float(sides[1])
        checks = [
            {'code': f'ROOM_MIN_AREA:{name}', 'status': 'PASS' if area + 1e-9 >= spec['min_area_m2'] else 'FAIL', 'observed': round(area, 3), 'minimum': spec['min_area_m2']},
            {'code': f'ROOM_MIN_WIDTH:{name}', 'status': 'PASS' if width + 1e-9 >= spec['min_width_m'] else 'FAIL', 'observed': round(width, 3), 'minimum': spec['min_width_m']},
            {'code': f'ROOM_MIN_DEPTH:{name}', 'status': 'PASS' if depth + 1e-9 >= spec['min_depth_m'] else 'FAIL', 'observed': round(depth, 3), 'minimum': spec['min_depth_m']},
        ]
        if spec['max_area_m2'] is not None:
            checks.append({'code': f'ROOM_MAX_AREA:{name}', 'status': 'PASS' if area <= spec['max_area_m2'] + 1e-9 else 'FAIL', 'observed': round(area, 3), 'maximum': spec['max_area_m2']})
        hard.extend(checks)

        exterior = _longest_line(geom.boundary.intersection(unit_polygon.boundary)) if geom is not None and not geom.is_empty else None
        exterior_opening = None
        if spec['exterior_opening_required']:
            exterior_opening = _center_segment(exterior, float(spec['exterior_opening_width_m']))
            hard.append({
                'code': f'EXTERIOR_OPENING:{name}',
                'status': 'PASS' if exterior_opening is not None else 'FAIL',
                'available_boundary_m': round(float(exterior.length), 3) if exterior is not None else 0.0,
                'required_width_m': spec['exterior_opening_width_m'],
            })
            if exterior_opening is not None:
                openings.append({'kind': 'EXTERIOR', 'room': name, 'width_m': spec['exterior_opening_width_m'], 'geometry': mapping(exterior_opening)})
        room_results.append({
            'name': name,
            'target_area_m2': spec['target_area_m2'],
            'area_m2': round(area, 3),
            'bbox_min_width_m': round(width, 3),
            'bbox_max_depth_m': round(depth, 3),
            'geometry': mapping(geom) if geom is not None and not geom.is_empty else None,
        })

    for rule in adjacencies:
        left = geometries[rule['a']]
        right = geometries[rule['b']]
        shared = _longest_line(left.boundary.intersection(right.boundary)) if not left.is_empty and not right.is_empty else None
        shared_length = float(shared.length) if shared is not None else 0.0
        adjacency_pass = shared_length + 1e-9 >= rule['min_shared_boundary_m'] and shared_length > 1e-9
        if rule['required']:
            hard.append({
                'code': f"ADJACENCY:{rule['a']}:{rule['b']}",
                'status': 'PASS' if adjacency_pass else 'FAIL',
                'shared_boundary_m': round(shared_length, 3),
                'minimum': rule['min_shared_boundary_m'],
            })
        opening = None
        if rule['opening_required']:
            opening = _center_segment(shared, float(rule['opening_width_m'])) if adjacency_pass else None
            hard.append({
                'code': f"INTERNAL_OPENING:{rule['a']}:{rule['b']}",
                'status': 'PASS' if opening is not None else 'FAIL',
                'available_boundary_m': round(shared_length, 3),
                'required_width_m': rule['opening_width_m'],
            })
            if opening is not None:
                openings.append({'kind': 'INTERNAL', 'rooms': [rule['a'], rule['b']], 'width_m': rule['opening_width_m'], 'geometry': mapping(opening)})
        graph_edges.append({'a': rule['a'], 'b': rule['b'], 'required': rule['required'], 'shared_boundary_m': round(shared_length, 3), 'satisfied': adjacency_pass})

    union = unary_union([g for g in geometries.values() if g is not None and not g.is_empty])
    overlap_area = 0.0
    names = sorted(geometries)
    for i, left_name in enumerate(names):
        for right_name in names[i + 1:]:
            overlap_area += float(geometries[left_name].intersection(geometries[right_name]).area)
    uncovered_area = max(0.0, float(unit_polygon.difference(union).area))
    hard.extend([
        {'code': 'ROOMS_NO_OVERLAP', 'status': 'PASS' if overlap_area <= 1e-8 else 'FAIL', 'observed_area_m2': round(overlap_area, 6)},
        {'code': 'ROOMS_COVER_UNIT', 'status': 'PASS' if uncovered_area <= 1e-6 else 'FAIL', 'uncovered_area_m2': round(uncovered_area, 6)},
    ])
    failures = [item for item in hard if item['status'] == 'FAIL']
    area_error = sum(abs(next(room['target_area_m2'] for room in rooms if room['name'] == result['name']) - result['area_m2']) for result in room_results)
    return {
        'status': 'PASS' if not failures else 'SHORTFALL',
        'axis': axis,
        'rooms': room_results,
        'graph': {'nodes': [item['name'] for item in room_results], 'edges': graph_edges},
        'openings': openings,
        'hard_results': hard,
        '_score': (len(failures), round(area_error, 6), 0 if axis == 'x' else 1),
    }


def solve_unit_room_graph(unit_polygon, room_program: list[dict], adjacencies: list[dict] | None = None) -> dict[str, Any]:
    """Solve a deterministic conceptual room graph inside an explicit metric unit polygon.

    The solver partitions the supplied unit geometry and checks explicit room
    dimensions, adjacency and opening requirements. It does not infer local
    building-code requirements, furniture, structure, MEP, fire egress,
    accessibility or façade rules.
    """
    if unit_polygon is None or unit_polygon.is_empty or not unit_polygon.is_valid or unit_polygon.geom_type != 'Polygon':
        raise ValueError('unit_polygon must be a valid non-empty Polygon in a metric CRS')
    rooms = _normalize_rooms(room_program)
    rules = _normalize_adjacencies(adjacencies, {item['name'] for item in rooms})
    by_name = {item['name']: item for item in rooms}
    order = _room_order(rooms, rules)
    variants = []
    for axis in ('x', 'y'):
        for candidate_order in (order, list(reversed(order))):
            geometries = _partition(unit_polygon, by_name, candidate_order, axis)
            result = _evaluate(unit_polygon, rooms, rules, geometries, axis)
            result['order'] = candidate_order
            variants.append(result)
    best = min(variants, key=lambda item: item['_score'])
    best.pop('_score', None)
    best.update({
        'solver_version': ROOM_SOLVER_VERSION,
        'unit_area_m2': round(float(unit_polygon.area), 3),
        'limitations': [
            'Floor-plan conceitual por partição determinística; não é projeto executivo nem aprovação legal.',
            'Dimensões, adjacências e larguras de aberturas são entradas explícitas; o motor não inventa norma local.',
            'Não resolve mobiliário, estrutura, MEP, incêndio, acessibilidade, iluminação/ventilação regulamentar ou fachada.',
            'A geometria de abertura representa apenas um segmento conceitual de conexão, não uma esquadria executiva.',
        ],
    })
    return best
