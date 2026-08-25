from pathlib import Path
import math
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'aitec-engine' / 'app'))

from terrain_solver import (  # noqa: E402
    TERRAIN_SOLVER_VERSION,
    analyze_terrain,
    build_tin,
    contour_segments,
    cut_fill_against_pad,
    plateau_candidates,
)


class TerrainSolverV20Tests(unittest.TestCase):
    def test_flat_tin_plateau_and_exact_cut(self):
        samples = [
            {'x': 0, 'y': 0, 'z': 10},
            {'x': 10, 'y': 0, 'z': 10},
            {'x': 10, 'y': 10, 'z': 10},
            {'x': 0, 'y': 10, 'z': 10},
        ]
        tin = build_tin(samples)
        self.assertEqual(tin['status'], 'CALCULATED')
        self.assertEqual(tin['solver_version'], TERRAIN_SOLVER_VERSION)
        self.assertEqual(tin['triangle_count'], 2)
        self.assertAlmostEqual(tin['surface_area_2d_m2'], 100.0, places=6)
        self.assertAlmostEqual(tin['slope_percent_max'], 0.0, places=6)
        plateaus = plateau_candidates(tin, max_slope_percent=1.0, min_area_m2=90)
        self.assertEqual(len(plateaus), 1)
        self.assertAlmostEqual(plateaus[0]['area_m2'], 100.0, places=6)
        earth = cut_fill_against_pad(tin, 8)
        self.assertEqual(earth['status'], 'CALCULATED_PRELIMINARY')
        self.assertAlmostEqual(earth['cut_m3'], 200.0, places=6)
        self.assertAlmostEqual(earth['fill_m3'], 0.0, places=6)

    def test_planar_slope_and_contour_are_reproducible(self):
        # z = 0.1*x => 10% slope and the 0.5m contour sits at x=5.
        samples = [
            {'x': 0, 'y': 0, 'z': 0},
            {'x': 10, 'y': 0, 'z': 1},
            {'x': 10, 'y': 10, 'z': 1},
            {'x': 0, 'y': 10, 'z': 0},
        ]
        tin = build_tin(samples)
        self.assertEqual(tin['triangle_count'], 2)
        for triangle in tin['triangles']:
            self.assertAlmostEqual(triangle['slope_percent'], 10.0, places=6)
            self.assertAlmostEqual(triangle['slope_degrees'], math.degrees(math.atan(0.1)), places=6)
        contours = [x for x in contour_segments(tin, 0.5) if abs(x['elevation_m'] - 0.5) < 1e-9]
        self.assertTrue(contours)
        for segment in contours:
            for x, _y in segment['coordinates']:
                self.assertAlmostEqual(x, 5.0, places=6)

    def test_mixed_plane_cut_and_fill_balance(self):
        # z=x over a 10x10 square, pad z=5. Symmetry gives 125m3 cut and 125m3 fill.
        samples = [
            {'x': 0, 'y': 0, 'z': 0},
            {'x': 10, 'y': 0, 'z': 10},
            {'x': 10, 'y': 10, 'z': 10},
            {'x': 0, 'y': 10, 'z': 0},
        ]
        earth = cut_fill_against_pad(build_tin(samples), 5)
        self.assertAlmostEqual(earth['cut_m3'], 125.0, places=5)
        self.assertAlmostEqual(earth['fill_m3'], 125.0, places=5)
        self.assertAlmostEqual(earth['net_m3'], 0.0, places=5)

    def test_insufficient_and_conflicting_samples_are_explicit(self):
        tin = build_tin([{'x': 0, 'y': 0, 'z': 1}, {'x': 1, 'y': 0, 'z': 2}])
        self.assertEqual(tin['status'], 'INSUFFICIENT_DATA')
        self.assertEqual(tin['triangle_count'], 0)
        with self.assertRaisesRegex(ValueError, 'conflicting elevation'):
            build_tin([
                {'x': 0, 'y': 0, 'z': 1},
                {'x': 0, 'y': 0, 'z': 2},
                {'x': 1, 'y': 0, 'z': 1},
                {'x': 0, 'y': 1, 'z': 1},
            ])

    def test_analyze_terrain_never_invents_pad(self):
        samples = [
            {'x': 0, 'y': 0, 'z': 2},
            {'x': 10, 'y': 0, 'z': 2},
            {'x': 0, 'y': 10, 'z': 2},
        ]
        result = analyze_terrain(samples, contour_interval_m=1, plateau_min_area_m2=1)
        self.assertEqual(result['status'], 'CALCULATED')
        self.assertIsNone(result['cut_fill'])
        with_pad = analyze_terrain(samples, pad_elevation_m=1)
        self.assertEqual(with_pad['cut_fill']['status'], 'CALCULATED_PRELIMINARY')


if __name__ == '__main__':
    unittest.main()
