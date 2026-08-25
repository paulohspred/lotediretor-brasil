from pathlib import Path
import sys
import unittest

from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'aitec-engine' / 'app'))

from room_solver import ROOM_SOLVER_VERSION, solve_unit_room_graph  # noqa: E402


ROOMS = [
    {'name': 'Living', 'target_area_m2': 80, 'min_area_m2': 70, 'min_width_m': 4, 'min_depth_m': 8, 'entry': True, 'exterior_opening_required': True, 'exterior_opening_width_m': 2.0},
    {'name': 'Kitchen', 'target_area_m2': 40, 'min_area_m2': 35, 'min_width_m': 3, 'min_depth_m': 8},
    {'name': 'Bath', 'target_area_m2': 20, 'min_area_m2': 18, 'min_width_m': 1.8, 'min_depth_m': 8},
    {'name': 'Bedroom', 'target_area_m2': 60, 'min_area_m2': 55, 'min_width_m': 3, 'min_depth_m': 8, 'exterior_opening_required': True, 'exterior_opening_width_m': 1.5},
]
ADJ = [
    {'a': 'Living', 'b': 'Kitchen', 'required': True, 'min_shared_boundary_m': 2, 'opening_required': True, 'opening_width_m': 1.2},
    {'a': 'Kitchen', 'b': 'Bath', 'required': True, 'min_shared_boundary_m': 1.5, 'opening_required': True, 'opening_width_m': 0.8},
    {'a': 'Bath', 'b': 'Bedroom', 'required': True, 'min_shared_boundary_m': 1.5, 'opening_required': True, 'opening_width_m': 0.8},
]


class RoomGraphV20Tests(unittest.TestCase):
    def test_room_graph_dimensions_adjacencies_and_openings(self):
        unit = box(0, 0, 20, 10)
        result = solve_unit_room_graph(unit, ROOMS, ADJ)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['solver_version'], ROOM_SOLVER_VERSION)
        self.assertEqual(len(result['rooms']), 4)
        self.assertEqual(len(result['graph']['edges']), 3)
        self.assertTrue(all(edge['satisfied'] for edge in result['graph']['edges']))
        self.assertEqual(sum(1 for x in result['openings'] if x['kind'] == 'INTERNAL'), 3)
        self.assertEqual(sum(1 for x in result['openings'] if x['kind'] == 'EXTERIOR'), 2)

        geometries = [shape(room['geometry']) for room in result['rooms']]
        for index, left in enumerate(geometries):
            self.assertTrue(unit.covers(left))
            for right in geometries[index + 1:]:
                self.assertLessEqual(left.intersection(right).area, 1e-9)
        self.assertLessEqual(unit.difference(geometries[0].union(geometries[1]).union(geometries[2]).union(geometries[3])).area, 1e-9)

    def test_unsatisfiable_complete_adjacency_graph_is_shortfall(self):
        unit = box(0, 0, 20, 10)
        names = [room['name'] for room in ROOMS]
        rules = []
        for i, left in enumerate(names):
            for right in names[i + 1:]:
                rules.append({'a': left, 'b': right, 'required': True, 'opening_required': False, 'min_shared_boundary_m': 0.5})
        result = solve_unit_room_graph(unit, ROOMS, rules)
        self.assertEqual(result['status'], 'SHORTFALL')
        self.assertTrue(any(x['code'].startswith('ADJACENCY:') and x['status'] == 'FAIL' for x in result['hard_results']))

    def test_exterior_opening_width_is_not_silently_shrunk(self):
        rooms = [dict(room) for room in ROOMS]
        rooms[0]['exterior_opening_width_m'] = 100.0
        result = solve_unit_room_graph(box(0, 0, 20, 10), rooms, ADJ)
        self.assertEqual(result['status'], 'SHORTFALL')
        gate = next(x for x in result['hard_results'] if x['code'] == 'EXTERIOR_OPENING:Living')
        self.assertEqual(gate['status'], 'FAIL')
        self.assertEqual(gate['required_width_m'], 100.0)

    def test_missing_explicit_opening_width_is_rejected(self):
        bad = [{'a': 'Living', 'b': 'Kitchen', 'required': True, 'opening_required': True}]
        with self.assertRaisesRegex(ValueError, 'requires explicit opening_width_m'):
            solve_unit_room_graph(box(0, 0, 20, 10), ROOMS, bad)

    def test_invalid_room_dimension_contract_is_rejected(self):
        rooms = [dict(ROOMS[0])]
        rooms[0]['max_area_m2'] = 10
        with self.assertRaisesRegex(ValueError, 'max_area_m2 cannot be below min_area_m2'):
            solve_unit_room_graph(box(0, 0, 20, 10), rooms, [])


if __name__ == '__main__':
    unittest.main()
