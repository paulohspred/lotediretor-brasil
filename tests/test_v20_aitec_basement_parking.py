from pathlib import Path
import sys
import unittest

from shapely.geometry import LineString, box, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'aitec-engine' / 'app'))

from basement_parking_solver import BASEMENT_PARKING_VERSION, solve_basement_parking  # noqa: E402


class BasementParkingV20Tests(unittest.TestCase):
    def test_valid_layout_respects_explicit_quotas_ramp_and_columns(self):
        garage = box(0, 0, 60, 60)
        result = solve_basement_parking(
            garage,
            required_spaces=20,
            accessible_spaces=2,
            ev_spaces=4,
            ramp_centerline=LineString([(4, 4), (24, 4)]),
            level_depth_m=3.0,
            max_ramp_slope_percent=18.0,
            ramp_width_m=5.0,
            column_spacing_x_m=8.0,
            column_spacing_y_m=8.0,
        )
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['solver_version'], BASEMENT_PARKING_VERSION)
        self.assertGreaterEqual(result['generated_spaces'], 20)
        self.assertGreaterEqual(result['accessible_generated'], 2)
        self.assertGreaterEqual(result['ev_generated'], 4)
        self.assertEqual(result['accessible_ev_overlap'], 2)
        self.assertEqual(result['ramp']['status'], 'PASS')
        self.assertLessEqual(result['ramp']['slope_percent'], 18.0)

        columns = unary_union([shape(g) for g in result['columns']])
        for stall in result['stalls']:
            geom = shape(stall['geometry'])
            self.assertTrue(garage.covers(geom))
            self.assertLessEqual(geom.intersection(columns).area, 1e-9)

    def test_steep_ramp_is_hard_failure_without_relaxing_input(self):
        result = solve_basement_parking(
            box(0, 0, 60, 60),
            required_spaces=4,
            accessible_spaces=0,
            ev_spaces=0,
            ramp_centerline=LineString([(5, 5), (15, 5)]),
            level_depth_m=3.0,
            max_ramp_slope_percent=20.0,
        )
        self.assertEqual(result['status'], 'SHORTFALL')
        self.assertAlmostEqual(result['ramp']['slope_percent'], 30.0, places=6)
        gate = next(x for x in result['hard_results'] if x['code'] == 'RAMP_MAX_SLOPE')
        self.assertEqual(gate['status'], 'FAIL')
        self.assertEqual(gate['maximum'], 20.0)

    def test_missing_ramp_is_explicit_failure(self):
        result = solve_basement_parking(
            box(0, 0, 40, 40),
            required_spaces=4,
            accessible_spaces=1,
            ev_spaces=1,
            ramp_centerline=None,
            level_depth_m=3.0,
            max_ramp_slope_percent=20.0,
        )
        self.assertEqual(result['status'], 'SHORTFALL')
        self.assertEqual(result['ramp']['status'], 'NOT_PROVIDED')
        self.assertTrue(any(x['code'] == 'RAMP_REQUIRED' and x['status'] == 'FAIL' for x in result['hard_results']))

    def test_small_garage_reports_capacity_shortfall(self):
        result = solve_basement_parking(
            box(0, 0, 18, 18),
            required_spaces=30,
            accessible_spaces=2,
            ev_spaces=2,
            ramp_centerline=LineString([(3, 3), (16, 3)]),
            level_depth_m=2.0,
            max_ramp_slope_percent=20.0,
            ramp_width_m=3.0,
            column_spacing_x_m=7.0,
            column_spacing_y_m=7.0,
        )
        self.assertEqual(result['status'], 'SHORTFALL')
        self.assertLess(result['generated_spaces'], 30)
        self.assertTrue(any(x['code'] == 'PARKING_TOTAL_MIN' and x['status'] == 'FAIL' for x in result['hard_results']))

    def test_invalid_explicit_quotas_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'cannot exceed required spaces'):
            solve_basement_parking(
                box(0, 0, 40, 40),
                required_spaces=2,
                accessible_spaces=3,
                ev_spaces=0,
                ramp_centerline=LineString([(4, 4), (24, 4)]),
                level_depth_m=3.0,
                max_ramp_slope_percent=20.0,
            )

    def test_fixed_exclusion_is_not_used_for_stalls(self):
        exclusion = box(20, 0, 40, 60)
        result = solve_basement_parking(
            box(0, 0, 60, 60),
            required_spaces=8,
            accessible_spaces=1,
            ev_spaces=1,
            ramp_centerline=LineString([(4, 4), (24, 4)]),
            level_depth_m=3.0,
            max_ramp_slope_percent=18.0,
            fixed_exclusions=[exclusion],
        )
        for stall in result['stalls']:
            self.assertLessEqual(shape(stall['geometry']).intersection(exclusion).area, 1e-9)


if __name__ == '__main__':
    unittest.main()
