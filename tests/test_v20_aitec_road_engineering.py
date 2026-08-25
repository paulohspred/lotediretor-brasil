from pathlib import Path
import sys
import unittest

from shapely.geometry import LineString, box, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'aitec-engine' / 'app'))

from road_engineering_solver import ROAD_SOLVER_VERSION, evaluate_road_engineering  # noqa: E402


class RoadEngineeringV20Tests(unittest.TestCase):
    def test_explicit_road_width_radius_grade_and_emergency_pass(self):
        parcel = box(0, 0, 50, 50)
        centerline = LineString([(3, 3), (3, 20), (20, 35), (35, 35)])
        result = evaluate_road_engineering(
            parcel,
            centerline,
            road_width_m=6.0,
            min_turn_radius_m=8.0,
            emergency_min_width_m=5.5,
            max_access_boundary_distance_m=3.1,
            max_grade_percent=8.0,
            vertex_elevations_m=[0.0, 1.0, 2.0, 2.5],
            emergency_required=True,
            emergency_turnaround_radius_m=5.0,
        )
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['solver_version'], ROAD_SOLVER_VERSION)
        self.assertTrue(parcel.covers(shape(result['surface_geometry'])))
        self.assertTrue(all(turn['status'] == 'PASS' for turn in result['turns']))
        self.assertTrue(all(grade['status'] == 'PASS' for grade in result['grades']))
        self.assertIsNotNone(result['emergency']['turnaround_geometry'])

    def test_sharp_turn_is_hard_failure(self):
        result = evaluate_road_engineering(
            box(0, 0, 30, 30),
            LineString([(3, 3), (3, 10), (10, 10)]),
            road_width_m=4.0,
            min_turn_radius_m=8.0,
            emergency_min_width_m=4.0,
            max_access_boundary_distance_m=3.1,
        )
        self.assertEqual(result['status'], 'SHORTFALL')
        gate = next(x for x in result['hard_results'] if x['code'] == 'ROAD_MIN_TURN_RADIUS')
        self.assertEqual(gate['status'], 'FAIL')
        self.assertLess(gate['observed_minimum_m'], 8.0)

    def test_grade_constraint_requires_elevation_data(self):
        result = evaluate_road_engineering(
            box(0, 0, 30, 30),
            LineString([(3, 3), (3, 20)]),
            road_width_m=4.0,
            min_turn_radius_m=5.0,
            emergency_min_width_m=4.0,
            max_access_boundary_distance_m=3.1,
            max_grade_percent=10.0,
            vertex_elevations_m=None,
        )
        self.assertEqual(result['status'], 'SHORTFALL')
        self.assertTrue(any(x['code'] == 'ROAD_GRADE_DATA' and x['status'] == 'FAIL' for x in result['hard_results']))

    def test_emergency_width_is_not_silently_relaxed(self):
        result = evaluate_road_engineering(
            box(0, 0, 40, 40),
            LineString([(2, 3), (2, 25)]),
            road_width_m=4.0,
            min_turn_radius_m=5.0,
            emergency_min_width_m=6.0,
            max_access_boundary_distance_m=3.1,
            emergency_required=True,
            emergency_turnaround_radius_m=4.0,
        )
        self.assertEqual(result['status'], 'SHORTFALL')
        gate = next(x for x in result['hard_results'] if x['code'] == 'EMERGENCY_MIN_WIDTH')
        self.assertEqual(gate['status'], 'FAIL')
        self.assertEqual(gate['minimum_m'], 6.0)

    def test_surface_outside_parcel_fails(self):
        result = evaluate_road_engineering(
            box(0, 0, 30, 30),
            LineString([(0.5, 0.5), (0.5, 20)]),
            road_width_m=6.0,
            min_turn_radius_m=5.0,
            emergency_min_width_m=5.0,
            max_access_boundary_distance_m=1.0,
        )
        self.assertEqual(result['status'], 'SHORTFALL')
        self.assertTrue(any(x['code'] == 'ROAD_SURFACE_INSIDE_PARCEL' and x['status'] == 'FAIL' for x in result['hard_results']))


if __name__ == '__main__':
    unittest.main()
