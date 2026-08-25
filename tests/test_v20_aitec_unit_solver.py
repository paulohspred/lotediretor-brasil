from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'aitec-engine' / 'app'))

from unit_solver import DESIGN_DNA_VERSION, compare_designs, solve_unit_distribution  # noqa: E402


FLOORS = [
    {'building': 1, 'floor': 1, 'net_area_m2': 320},
    {'building': 1, 'floor': 2, 'net_area_m2': 320},
    {'building': 1, 'floor': 3, 'net_area_m2': 280},
]
UNIT_TYPES = [
    {'name': 'Studio', 'target_area_m2': 40, 'min_count': 3, 'target_share': 0.45},
    {'name': '2D', 'target_area_m2': 70, 'min_count': 2, 'target_share': 0.35},
    {'name': '3D', 'target_area_m2': 95, 'min_count': 1, 'max_count': 3, 'target_share': 0.20},
]


class UnitSolverV20Tests(unittest.TestCase):
    def test_deterministic_distribution_and_dna(self):
        first = solve_unit_distribution(FLOORS, UNIT_TYPES, min_total_units=8, solver_seed=17)
        second = solve_unit_distribution(FLOORS, UNIT_TYPES, min_total_units=8, solver_seed=17)
        self.assertEqual(first['status'], 'PASS')
        self.assertEqual(first['floors'], second['floors'])
        self.assertEqual(first['design_dna'], second['design_dna'])
        self.assertEqual(first['design_dna']['version'], DESIGN_DNA_VERSION)
        self.assertEqual(len(first['design_dna']['content_fingerprint']), 64)
        self.assertGreaterEqual(first['total_units'], 8)
        self.assertTrue(all(f['used_private_area_m2'] <= f['net_area_m2'] for f in first['floors']))

    def test_exact_floor_type_lock_survives_branch_regenerate(self):
        base = solve_unit_distribution(FLOORS, UNIT_TYPES, min_total_units=8, solver_seed=1)
        locks = [{'building': 1, 'floor': 1, 'unit_type': 'Studio', 'count': 2}]
        branch = solve_unit_distribution(
            FLOORS,
            UNIT_TYPES,
            min_total_units=9,
            locks=locks,
            parent_design_dna=base['design_dna'],
            solver_seed=999,
        )
        floor1 = next(f for f in branch['floors'] if f['building'] == 1 and f['floor'] == 1)
        studio = next(a for a in floor1['assignments'] if a['unit_type'] == 'Studio')
        self.assertEqual(studio['count'], 2)
        self.assertTrue(studio['locked'])
        self.assertEqual(branch['design_dna']['parent_content_fingerprint'], base['design_dna']['content_fingerprint'])
        self.assertNotEqual(branch['design_dna']['lineage_fingerprint'], base['design_dna']['lineage_fingerprint'])

    def test_impossible_program_is_explicit_shortfall(self):
        tiny = [{'building': 1, 'floor': 1, 'net_area_m2': 55}]
        types = [
            {'name': 'A', 'target_area_m2': 40, 'min_count': 2, 'target_share': 1.0},
        ]
        result = solve_unit_distribution(tiny, types, min_total_units=2)
        self.assertEqual(result['status'], 'SHORTFALL')
        failures = [x['code'] for x in result['hard_results'] if x['status'] == 'FAIL']
        self.assertIn('UNIT_MIN:A', failures)
        self.assertIn('PROGRAM_MIN_UNITS', failures)

    def test_lock_over_capacity_fails_without_mutating_lock(self):
        result = solve_unit_distribution(
            [{'building': 1, 'floor': 1, 'net_area_m2': 100}],
            [{'name': 'A', 'target_area_m2': 40, 'target_share': 1.0}],
            locks=[{'building': 1, 'floor': 1, 'unit_type': 'A', 'count': 3}],
        )
        self.assertEqual(result['status'], 'SHORTFALL')
        floor = result['floors'][0]
        assignment = floor['assignments'][0]
        self.assertEqual(assignment['count'], 3)
        self.assertTrue(assignment['locked'])
        self.assertGreater(floor['used_private_area_m2'], floor['net_area_m2'])
        self.assertTrue(any(x['code'].startswith('LOCK:') and x['status'] == 'FAIL' for x in result['hard_results']))

    def test_semantic_design_diff(self):
        before = solve_unit_distribution(FLOORS, UNIT_TYPES, min_total_units=8, solver_seed=1)
        after = solve_unit_distribution(
            FLOORS,
            UNIT_TYPES,
            min_total_units=8,
            locks=[{'building': 1, 'floor': 1, 'unit_type': 'Studio', 'count': 1}],
            parent_design_dna=before['design_dna'],
            solver_seed=1,
        )
        diff = compare_designs(before, after)
        self.assertFalse(diff['same_content'])
        self.assertTrue(diff['changes'])
        self.assertTrue(all({'building', 'floor', 'unit_type', 'before_count', 'after_count', 'delta'} <= set(x) for x in diff['changes']))

    def test_unknown_lock_reference_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unknown floor'):
            solve_unit_distribution(
                FLOORS,
                UNIT_TYPES,
                locks=[{'building': 9, 'floor': 9, 'unit_type': 'Studio', 'count': 1}],
            )


if __name__ == '__main__':
    unittest.main()
