from __future__ import annotations

import math
from typing import Any

from shapely.affinity import translate
from shapely.geometry import box, mapping

BUILDING_SOLVER_VERSION = 'aitec-building-v20.1'


def _square(area_m2: float):
    side = math.sqrt(float(area_m2))
    return box(-side / 2.0, -side / 2.0, side / 2.0, side / 2.0)


def _find_core(footprint, core_area_m2: float):
    if core_area_m2 <= 0:
        raise ValueError('core_area_m2 must be > 0')
    side = math.sqrt(core_area_m2)
    minx, miny, maxx, maxy = footprint.bounds
    candidates = [
        footprint.representative_point(),
        footprint.centroid,
    ]
    for fx, fy in ((0.25, 0.25), (0.5, 0.25), (0.75, 0.25), (0.25, 0.5), (0.5, 0.5), (0.75, 0.5), (0.25, 0.75), (0.5, 0.75), (0.75, 0.75)):
        candidates.append(type(footprint.representative_point())(minx + (maxx - minx) * fx, miny + (maxy - miny) * fy))
    template = _square(core_area_m2)
    for point in candidates:
        candidate = translate(template, xoff=point.x, yoff=point.y)
        if footprint.covers(candidate):
            return candidate
    return None


def _component_specs(
    stairs_per_building: int,
    stair_area_m2: float,
    elevators_per_building: int,
    elevator_area_m2: float,
    shafts_per_building: int,
    shaft_area_m2: float,
) -> list[dict]:
    counts = {
        'STAIR': int(stairs_per_building),
        'ELEVATOR': int(elevators_per_building),
        'SHAFT': int(shafts_per_building),
    }
    areas = {
        'STAIR': float(stair_area_m2),
        'ELEVATOR': float(elevator_area_m2),
        'SHAFT': float(shaft_area_m2),
    }
    if any(value < 0 for value in counts.values()):
        raise ValueError('vertical-system counts must be >= 0')
    for kind, count in counts.items():
        if count and areas[kind] <= 0:
            raise ValueError(f'{kind.lower()}_area_m2 must be > 0 when count is positive')
    out = []
    for kind in ('STAIR', 'ELEVATOR', 'SHAFT'):
        for index in range(counts[kind]):
            out.append({'kind': kind, 'index': index + 1, 'area_m2': areas[kind]})
    return out


def _pack_components(core, specs: list[dict], clearance_m: float) -> tuple[list[dict], bool]:
    if clearance_m < 0:
        raise ValueError('component_clearance_m must be >= 0')
    if not specs:
        return [], True
    minx, miny, maxx, maxy = core.bounds
    margin = float(clearance_m)
    cursor_x = minx + margin
    cursor_y = miny + margin
    row_height = 0.0
    packed = []
    for spec in sorted(specs, key=lambda item: (-item['area_m2'], item['kind'], item['index'])):
        side = math.sqrt(spec['area_m2'])
        if cursor_x + side > maxx - margin + 1e-9:
            cursor_x = minx + margin
            cursor_y += row_height + margin
            row_height = 0.0
        geom = box(cursor_x, cursor_y, cursor_x + side, cursor_y + side)
        if cursor_y + side > maxy - margin + 1e-9 or not core.covers(geom):
            return packed, False
        packed.append({**spec, 'geometry': geom})
        cursor_x += side + margin
        row_height = max(row_height, side)
    return packed, True


def solve_building_system(
    footprints: list,
    floors: int,
    core_area_m2: float,
    circulation_width_m: float,
    stairs_per_building: int,
    stair_area_m2: float,
    elevators_per_building: int,
    elevator_area_m2: float,
    shafts_per_building: int,
    shaft_area_m2: float,
    floor_height_m: float = 3.0,
    component_clearance_m: float = 0.2,
) -> dict[str, Any]:
    """Create a deterministic conceptual vertical-system layout per building.

    Counts and component areas are explicit inputs. The solver never infers
    statutory stair/elevator/shaft requirements and does not claim code, fire,
    accessibility, structural or egress compliance.
    """
    if floors < 1:
        raise ValueError('floors must be >= 1')
    if floor_height_m <= 0 or circulation_width_m <= 0:
        raise ValueError('floor_height_m and circulation_width_m must be > 0')
    if not footprints:
        raise ValueError('at least one building footprint is required')
    specs = _component_specs(
        stairs_per_building,
        stair_area_m2,
        elevators_per_building,
        elevator_area_m2,
        shafts_per_building,
        shaft_area_m2,
    )
    required_component_area = sum(item['area_m2'] for item in specs)
    results = []
    hard_results = []
    total_core = total_circulation = total_net = 0.0

    for index, footprint in enumerate(footprints, start=1):
        if footprint is None or footprint.is_empty or not footprint.is_valid or footprint.geom_type not in ('Polygon', 'MultiPolygon'):
            raise ValueError(f'invalid building footprint:{index}')
        core = _find_core(footprint, float(core_area_m2))
        if core is None:
            hard_results.append({'code': f'CORE_FIT:{index}', 'status': 'FAIL', 'required_area_m2': float(core_area_m2)})
            results.append({
                'building': index,
                'status': 'CORE_DOES_NOT_FIT',
                'floors': floors,
                'floor_plate_area_m2': round(float(footprint.area), 2),
            })
            continue

        packed, packed_ok = _pack_components(core, specs, component_clearance_m)
        components_area = sum(float(item['geometry'].area) for item in packed)
        circulation = core.buffer(float(circulation_width_m), join_style=2).intersection(footprint).difference(core)
        net_per_floor = max(0.0, float(footprint.area) - float(core.area) - float(circulation.area))
        hard_results.extend([
            {
                'code': f'CORE_FIT:{index}',
                'status': 'PASS',
                'observed_area_m2': round(float(core.area), 3),
                'required_area_m2': float(core_area_m2),
            },
            {
                'code': f'VERTICAL_COMPONENTS_FIT:{index}',
                'status': 'PASS' if packed_ok and len(packed) == len(specs) else 'FAIL',
                'required_component_area_m2': round(required_component_area, 3),
                'packed_component_area_m2': round(components_area, 3),
            },
            {
                'code': f'NET_FLOOR_AREA_POSITIVE:{index}',
                'status': 'PASS' if net_per_floor > 0 else 'FAIL',
                'observed_net_area_m2': round(net_per_floor, 3),
            },
        ])

        floor_records = []
        for floor_number in range(1, floors + 1):
            floor_records.append({
                'floor': floor_number,
                'gross_floor_plate_area_m2': round(float(footprint.area), 3),
                'core_area_m2': round(float(core.area), 3),
                'circulation_area_m2': round(float(circulation.area), 3),
                'net_program_area_m2': round(net_per_floor, 3),
                'core_geometry': mapping(core),
                'circulation_geometry': mapping(circulation),
                'vertical_components': [
                    {
                        'kind': item['kind'],
                        'index': item['index'],
                        'area_m2': round(float(item['geometry'].area), 3),
                        'geometry': mapping(item['geometry']),
                    }
                    for item in packed
                ],
            })

        building_status = 'PRELIMINARY' if packed_ok and net_per_floor > 0 else 'INVALID'
        results.append({
            'building': index,
            'status': building_status,
            'floors': floors,
            'height_m': round(floors * floor_height_m, 3),
            'floor_plate_area_m2': round(float(footprint.area), 3),
            'core_area_m2': round(float(core.area), 3),
            'circulation_area_m2': round(float(circulation.area), 3),
            'net_program_area_per_floor_m2': round(net_per_floor, 3),
            'vertical_components_per_floor': len(packed),
            'floor_records': floor_records,
        })
        total_core += float(core.area) * floors
        total_circulation += float(circulation.area) * floors
        total_net += net_per_floor * floors

    failed = [item for item in hard_results if item['status'] == 'FAIL']
    return {
        'status': 'PASS' if not failed and len(results) == len(footprints) else 'FAIL',
        'solver_version': BUILDING_SOLVER_VERSION,
        'building_count': len(footprints),
        'floors_per_building': floors,
        'height_m': round(floors * floor_height_m, 3),
        'inputs': {
            'core_area_m2': float(core_area_m2),
            'circulation_width_m': float(circulation_width_m),
            'stairs_per_building': int(stairs_per_building),
            'stair_area_m2': float(stair_area_m2),
            'elevators_per_building': int(elevators_per_building),
            'elevator_area_m2': float(elevator_area_m2),
            'shafts_per_building': int(shafts_per_building),
            'shaft_area_m2': float(shaft_area_m2),
            'component_clearance_m': float(component_clearance_m),
        },
        'total_core_area_m2': round(total_core, 3),
        'total_circulation_area_m2': round(total_circulation, 3),
        'total_net_program_area_m2': round(total_net, 3),
        'buildings': results,
        'hard_results': hard_results,
        'limitations': [
            'Quantidades e áreas de escadas/elevadores/shafts são entradas explícitas; o solver não inventa requisitos normativos.',
            'Geometrias são pré-dimensionamento conceitual e não comprovam incêndio, acessibilidade, estrutura, egress, ventilação ou código local.',
            'Não substitui projeto arquitetônico, estrutural, instalações ou aprovação profissional.',
        ],
    }
