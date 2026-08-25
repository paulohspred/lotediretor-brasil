from pathlib import Path
import sys
import unittest

from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'aitec-engine' / 'app'))

from building_solver import BUILDING_SOLVER_VERSION, solve_building_system  # noqa: E402


class BuildingSolverV20Tests(unittest.TestCase):
    def test_explicit_vertical_systems_fit_and_repeat_by_floor(self):
        footprint = box(0, 0, 20, 20)
        result = solve_building_system(
            [footprint],
            floors=5,
            core_area_m2=100,
            circulation_width_m=1.8,
            stairs_per_building=2,
            stair_area_m2=16,
            elevators_per_building=2,
            elevator_area_m2=4,
            shafts_per_building=2,
            shaft_area_m2=2.25,
            floor_height_m=3.1,
        )
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['solver_version'], BUILDING_SOLVER_VERSION)
        building = result['buildings'][0]
        self.assertEqual(building['status'], 'PRELIMINARY')
        self.assertEqual(len(building['floor_records']), 5)
        self.assertEqual(building['vertical_components_per_floor'], 6)
        self.assertAlmostEqual(building['height_m'], 15.5, places=6)
        for floor in building['floor_records']:
            core = shape(floor['core_geometry'])
            circulation = shape(floor['circulation_geometry'])
            self.assertTrue(footprint.covers(core))
            self.assertTrue(footprint.covers(circulation))
            # The circulation ring may share the core boundary; the geometric
            # invariant is zero area overlap, not disjoint boundaries.
            self.assertAlmostEqual(core.intersection(circulation).area, 0.0, places=9)
            for component in floor['vertical_components']:
                self.assertTrue(core.covers(shape(component['geometry'])))

    def test_small_footprint_fails_core_fit_explicitly(self):
        result = solve_building_system(
            [box(0, 0, 5, 5)],
            floors=2,
            core_area_m2=36,
            circulation_width_m=1.2,
            stairs_per_building=1,
            stair_area_m2=9,
            elevators_per_building=0,
            elevator_area_m2=0,
            shafts_per_building=0,
            shaft_area_m2=0,
        )
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['buildings'][0]['status'], 'CORE_DOES_NOT_FIT')
        self.assertTrue(any(x['code'] == 'CORE_FIT:1' and x['status'] == 'FAIL' for x in result['hard_results']))

    def test_component_overload_fails_without_shrinking_requirements(self):
        result = solve_building_system(
            [box(0, 0, 20, 20)],
            floors=3,
            core_area_m2=64,
            circulation_width_m=1.5,
            stairs_per_building=4,
            stair_area_m2=25,
            elevators_per_building=2,
            elevator_area_m2=9,
            shafts_per_building=2,
            shaft_area_m2=4,
            component_clearance_m=0.4,
        )
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(any(x['code'] == 'VERTICAL_COMPONENTS_FIT:1' and x['status'] == 'FAIL' for x in result['hard_results']))

    def test_zero_counts_do_not_invent_vertical_components(self):
        result = solve_building_system(
            [box(0, 0, 15, 15)],
            floors=1,
            core_area_m2=25,
            circulation_width_m=1,
            stairs_per_building=0,
            stair_area_m2=0,
            elevators_per_building=0,
            elevator_area_m2=0,
            shafts_per_building=0,
            shaft_area_m2=0,
        )
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['buildings'][0]['vertical_components_per_floor'], 0)
        self.assertEqual(result['buildings'][0]['floor_records'][0]['vertical_components'], [])

    def test_multiple_buildings_are_deterministic(self):
        args = dict(
            floors=2,
            core_area_m2=49,
            circulation_width_m=1.2,
            stairs_per_building=1,
            stair_area_m2=12,
            elevators_per_building=1,
            elevator_area_m2=4,
            shafts_per_building=1,
            shaft_area_m2=2,
        )
        footprints = [box(0, 0, 18, 18), box(30, 0, 50, 16)]
        first = solve_building_system(footprints, **args)
        second = solve_building_system(footprints, **args)
        self.assertEqual(first, second)
        self.assertEqual(first['building_count'], 2)
        self.assertEqual(first['status'], 'PASS')


if __name__ == '__main__':
    unittest.main()
