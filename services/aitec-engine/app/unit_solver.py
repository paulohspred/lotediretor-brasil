from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

DESIGN_DNA_VERSION = 'aitec-design-dna-v20.1'
SOLVER_ID = 'conceptual-unit-distribution-v20.1'


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def _normalize_unit_types(unit_types: list[dict]) -> list[dict]:
    if not unit_types:
        raise ValueError('unit_types are required')
    out = []
    seen = set()
    for index, raw in enumerate(unit_types):
        name = str(raw.get('name') or raw.get('type') or f'TYPE-{index + 1}').strip()
        if not name:
            raise ValueError('unit type name cannot be empty')
        if name in seen:
            raise ValueError(f'duplicate unit type:{name}')
        seen.add(name)
        area = float(raw.get('target_area_m2') or raw.get('area_m2') or 0)
        if area <= 0:
            raise ValueError(f'unit type {name} requires positive target_area_m2')
        minimum = max(0, int(raw.get('min_count') or raw.get('minimum') or 0))
        maximum_raw = raw.get('max_count')
        maximum = None if maximum_raw is None else int(maximum_raw)
        if maximum is not None and maximum < minimum:
            raise ValueError(f'unit type {name} max_count cannot be below min_count')
        share_raw = raw.get('target_share')
        share = None if share_raw is None else max(0.0, float(share_raw))
        out.append({
            'name': name,
            'target_area_m2': area,
            'min_count': minimum,
            'max_count': maximum,
            'target_share': share,
        })

    total_share = sum(float(item['target_share'] or 0) for item in out)
    if total_share <= 0:
        equal = 1.0 / len(out)
        for item in out:
            item['target_share'] = equal
    else:
        for item in out:
            item['target_share'] = float(item['target_share'] or 0) / total_share
    return out


def _normalize_floors(floors: list[dict]) -> list[dict]:
    if not floors:
        raise ValueError('floors are required')
    out = []
    seen = set()
    for raw in floors:
        building = int(raw.get('building') or raw.get('building_id') or 0)
        floor = int(raw.get('floor') or raw.get('level') or 0)
        net = float(raw.get('net_area_m2') or raw.get('usable_area_m2') or 0)
        if building < 1 or floor < 1:
            raise ValueError('building and floor must be >= 1')
        if net < 0:
            raise ValueError('net_area_m2 must be >= 0')
        key = (building, floor)
        if key in seen:
            raise ValueError(f'duplicate floor:{building}:{floor}')
        seen.add(key)
        out.append({'building': building, 'floor': floor, 'net_area_m2': net})
    return sorted(out, key=lambda item: (item['building'], item['floor']))


def _normalize_locks(locks: list[dict] | None) -> list[dict]:
    aggregated: dict[tuple[int, int, str], int] = defaultdict(int)
    for raw in locks or []:
        building = int(raw.get('building') or 0)
        floor = int(raw.get('floor') or 0)
        unit_type = str(raw.get('unit_type') or raw.get('name') or '').strip()
        count = int(raw.get('count') or 0)
        if building < 1 or floor < 1 or not unit_type or count < 0:
            raise ValueError('locks require building>=1, floor>=1, unit_type and count>=0')
        aggregated[(building, floor, unit_type)] += count
    return [
        {'building': key[0], 'floor': key[1], 'unit_type': key[2], 'count': count}
        for key, count in sorted(aggregated.items())
    ]


def solve_unit_distribution(
    floors: list[dict],
    unit_types: list[dict],
    min_total_units: int | None = None,
    locks: list[dict] | None = None,
    parent_design_dna: dict | None = None,
    solver_seed: int = 0,
) -> dict:
    """Distribute explicit unit types across explicit floor net areas.

    This is a deterministic *program/unit distribution* solver. It does not
    invent rooms, façades, shafts, doors, structure, fire egress or statutory
    dimensions. Locked assignments are exact for the locked floor/type key and
    therefore survive regenerate/branch operations.
    """
    normalized_floors = _normalize_floors(floors)
    normalized_types = _normalize_unit_types(unit_types)
    normalized_locks = _normalize_locks(locks)
    if min_total_units is not None and int(min_total_units) < 0:
        raise ValueError('min_total_units must be >= 0')

    floor_keys = {(f['building'], f['floor']) for f in normalized_floors}
    type_by_name = {item['name']: item for item in normalized_types}
    for lock in normalized_locks:
        if (lock['building'], lock['floor']) not in floor_keys:
            raise ValueError(f"lock references unknown floor:{lock['building']}:{lock['floor']}")
        if lock['unit_type'] not in type_by_name:
            raise ValueError(f"lock references unknown unit type:{lock['unit_type']}")

    floor_state: dict[tuple[int, int], dict] = {
        (f['building'], f['floor']): {
            'building': f['building'],
            'floor': f['floor'],
            'net_area_m2': f['net_area_m2'],
            'used_area_m2': 0.0,
            'assignments': defaultdict(int),
        }
        for f in normalized_floors
    }
    locked_keys = {(l['building'], l['floor'], l['unit_type']) for l in normalized_locks}
    counts = {name: 0 for name in type_by_name}
    hard_results = []

    for lock in normalized_locks:
        state = floor_state[(lock['building'], lock['floor'])]
        unit = type_by_name[lock['unit_type']]
        area = lock['count'] * unit['target_area_m2']
        state['assignments'][lock['unit_type']] = lock['count']
        state['used_area_m2'] += area
        counts[lock['unit_type']] += lock['count']
        hard_results.append({
            'code': f"LOCK:{lock['building']}:{lock['floor']}:{lock['unit_type']}",
            'status': 'PASS' if state['used_area_m2'] <= state['net_area_m2'] + 1e-9 else 'FAIL',
            'observed_count': lock['count'],
            'locked_count': lock['count'],
        })

    def can_add(state: dict, unit: dict) -> bool:
        key = (state['building'], state['floor'], unit['name'])
        if key in locked_keys:
            return False
        maximum = unit['max_count']
        if maximum is not None and counts[unit['name']] >= maximum:
            return False
        return state['used_area_m2'] + unit['target_area_m2'] <= state['net_area_m2'] + 1e-9

    def best_floor_for(unit: dict) -> dict | None:
        candidates = [state for state in floor_state.values() if can_add(state, unit)]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda state: (
                state['net_area_m2'] - state['used_area_m2'],
                -state['building'],
                -state['floor'],
            ),
        )

    # Hard program minima are satisfied first.
    for unit in normalized_types:
        while counts[unit['name']] < unit['min_count']:
            state = best_floor_for(unit)
            if state is None:
                break
            state['assignments'][unit['name']] += 1
            state['used_area_m2'] += unit['target_area_m2']
            counts[unit['name']] += 1

    total_net = sum(f['net_area_m2'] for f in normalized_floors)
    guard = 0
    while guard < 200000:
        guard += 1
        candidates = []
        for index, unit in enumerate(normalized_types):
            state = best_floor_for(unit)
            if state is None:
                continue
            target_private_area = total_net * float(unit['target_share'])
            current_private_area = counts[unit['name']] * unit['target_area_m2']
            deficit = target_private_area - current_private_area
            candidates.append((deficit, -unit['target_area_m2'], -index, unit, state))
        if not candidates:
            break
        _, _, _, unit, state = max(candidates, key=lambda item: item[:3])
        state['assignments'][unit['name']] += 1
        state['used_area_m2'] += unit['target_area_m2']
        counts[unit['name']] += 1

    for unit in normalized_types:
        count = counts[unit['name']]
        hard_results.append({
            'code': f"UNIT_MIN:{unit['name']}",
            'status': 'PASS' if count >= unit['min_count'] else 'FAIL',
            'observed': count,
            'minimum': unit['min_count'],
        })
        if unit['max_count'] is not None:
            hard_results.append({
                'code': f"UNIT_MAX:{unit['name']}",
                'status': 'PASS' if count <= unit['max_count'] else 'FAIL',
                'observed': count,
                'maximum': unit['max_count'],
            })

    total_units = sum(counts.values())
    if min_total_units is not None:
        hard_results.append({
            'code': 'PROGRAM_MIN_UNITS',
            'status': 'PASS' if total_units >= int(min_total_units) else 'FAIL',
            'observed': total_units,
            'minimum': int(min_total_units),
        })

    floor_results = []
    for key in sorted(floor_state):
        state = floor_state[key]
        assignments = [
            {
                'unit_type': name,
                'count': int(count),
                'private_area_m2': round(count * type_by_name[name]['target_area_m2'], 2),
                'locked': (state['building'], state['floor'], name) in locked_keys,
            }
            for name, count in sorted(state['assignments'].items())
            if count > 0
        ]
        used = float(state['used_area_m2'])
        floor_results.append({
            'building': state['building'],
            'floor': state['floor'],
            'net_area_m2': round(float(state['net_area_m2']), 2),
            'used_private_area_m2': round(used, 2),
            'unallocated_area_m2': round(max(0.0, float(state['net_area_m2']) - used), 2),
            'unit_count': sum(item['count'] for item in assignments),
            'assignments': assignments,
        })

    type_results = []
    total_private_area = 0.0
    for unit in normalized_types:
        count = counts[unit['name']]
        private = count * unit['target_area_m2']
        total_private_area += private
        type_results.append({
            **unit,
            'count': count,
            'private_area_m2': round(private, 2),
            'achieved_share': round(private / total_private_area, 6) if total_private_area else 0.0,
        })
    # Recompute shares against the final total after all types are known.
    for item in type_results:
        item['achieved_share'] = round(item['private_area_m2'] / total_private_area, 6) if total_private_area else 0.0

    failed = [result for result in hard_results if result['status'] == 'FAIL']
    content = {
        'solver': SOLVER_ID,
        'floors': normalized_floors,
        'unit_types': normalized_types,
        'locks': normalized_locks,
        'min_total_units': None if min_total_units is None else int(min_total_units),
        'solver_seed': int(solver_seed),
        'floor_results': floor_results,
    }
    content_fingerprint = _fingerprint(content)
    parent_content_fingerprint = None
    if isinstance(parent_design_dna, dict):
        parent_content_fingerprint = parent_design_dna.get('content_fingerprint') or parent_design_dna.get('fingerprint')
    lock_fingerprint = _fingerprint(normalized_locks)
    lineage_fingerprint = _fingerprint({
        'version': DESIGN_DNA_VERSION,
        'content_fingerprint': content_fingerprint,
        'parent_content_fingerprint': parent_content_fingerprint,
        'lock_fingerprint': lock_fingerprint,
    })

    return {
        'status': 'PASS' if not failed else 'SHORTFALL',
        'solver': SOLVER_ID,
        'total_units': total_units,
        'total_net_area_m2': round(total_net, 2),
        'total_private_area_m2': round(total_private_area, 2),
        'unallocated_area_m2': round(max(0.0, total_net - total_private_area), 2),
        'unit_types': type_results,
        'floors': floor_results,
        'locks': normalized_locks,
        'hard_results': hard_results,
        'design_dna': {
            'version': DESIGN_DNA_VERSION,
            'content_fingerprint': content_fingerprint,
            'lineage_fingerprint': lineage_fingerprint,
            'parent_content_fingerprint': parent_content_fingerprint,
            'lock_fingerprint': lock_fingerprint,
            'solver_seed': int(solver_seed),
        },
        'limitations': [
            'Distribuição conceitual de tipologias por área útil; não gera planta arquitetônica nem ambientes.',
            'Não inventa fachada, iluminação/ventilação, shafts, estrutura, incêndio, acessibilidade ou dimensões legais locais.',
            'Locks preservam contagens exatas apenas para a chave building/floor/unit_type explicitamente travada.',
        ],
    }


def compare_designs(before: dict, after: dict) -> dict:
    """Return a deterministic semantic diff between two unit-solver results."""
    def assignment_map(result: dict) -> dict[tuple[int, int, str], int]:
        out = {}
        for floor in result.get('floors') or []:
            for assignment in floor.get('assignments') or []:
                out[(int(floor['building']), int(floor['floor']), str(assignment['unit_type']))] = int(assignment['count'])
        return out

    left = assignment_map(before)
    right = assignment_map(after)
    changes = []
    for key in sorted(set(left) | set(right)):
        old = left.get(key, 0)
        new = right.get(key, 0)
        if old == new:
            continue
        changes.append({
            'building': key[0],
            'floor': key[1],
            'unit_type': key[2],
            'before_count': old,
            'after_count': new,
            'delta': new - old,
        })
    return {
        'same_content': (before.get('design_dna') or {}).get('content_fingerprint') == (after.get('design_dna') or {}).get('content_fingerprint'),
        'before_content_fingerprint': (before.get('design_dna') or {}).get('content_fingerprint'),
        'after_content_fingerprint': (after.get('design_dna') or {}).get('content_fingerprint'),
        'changes': changes,
    }
