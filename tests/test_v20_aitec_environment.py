from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'aitec-engine' / 'app'))

from environment_solver import ENVIRONMENT_SOLVER_VERSION, analyze_environment, analyze_noise  # noqa: E402


class EnvironmentV20Tests(unittest.TestCase):
    def test_all_explicit_thresholds_pass(self):
        result = analyze_environment(
            solar={
                'surfaces': [{'name': 'roof', 'area_m2': 100, 'tilt_deg': 0, 'azimuth_deg': 0, 'shading_factor': 1}],
                'sun_samples': [{'altitude_deg': 60, 'azimuth_deg': 0, 'weight': 1}],
                'min_exposure_index': 0.8,
            },
            daylight={
                'rooms': [{'name': 'living', 'floor_area_m2': 40, 'opening_area_m2': 8, 'transmittance': 0.8, 'sky_view_factor': 0.8}],
                'min_daylight_proxy': 0.1,
            },
            noise={
                'sources': [{'name': 'road', 'x': 0, 'y': 0, 'reference_db': 70, 'reference_distance_m': 1, 'additional_loss_db': 5}],
                'receptors': [{'name': 'facade', 'x': 20, 'y': 0}],
                'max_noise_db': 45,
            },
            wind={
                'scenarios': [{'name': 'prevailing', 'speed_mps': 5, 'weight': 1, 'exposure_factor': 1.1}],
                'receptors': [{'name': 'entrance', 'shelter_factor': 0.6}],
                'max_comfort_speed_mps': 4.0,
            },
        )
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['solver_version'], ENVIRONMENT_SOLVER_VERSION)
        self.assertGreater(result['solar']['exposure_index'], 0.8)
        self.assertGreater(result['daylight']['minimum_proxy'], 0.1)
        self.assertLess(result['noise']['maximum_db'], 45)
        self.assertLess(result['wind']['maximum_speed_mps'], 4.0)

    def test_missing_threshold_never_becomes_pass(self):
        result = analyze_environment(
            solar={
                'surfaces': [{'name': 'roof', 'area_m2': 50, 'tilt_deg': 0, 'azimuth_deg': 0}],
                'sun_samples': [{'altitude_deg': 45, 'azimuth_deg': 90, 'weight': 1}],
            }
        )
        self.assertEqual(result['status'], 'UNVERIFIED')
        self.assertEqual(result['solar']['status'], 'UNVERIFIED')

    def test_noise_sources_are_combined_logarithmically(self):
        one = analyze_noise(
            sources=[{'x': 0, 'y': 0, 'reference_db': 60, 'reference_distance_m': 1}],
            receptors=[{'x': 10, 'y': 0}],
            max_noise_db=50,
        )
        two = analyze_noise(
            sources=[
                {'x': 0, 'y': 0, 'reference_db': 60, 'reference_distance_m': 1},
                {'x': 0, 'y': 0, 'reference_db': 60, 'reference_distance_m': 1},
            ],
            receptors=[{'x': 10, 'y': 0}],
            max_noise_db=50,
        )
        self.assertGreater(two['maximum_db'], one['maximum_db'])
        self.assertAlmostEqual(two['maximum_db'] - one['maximum_db'], 3.01, delta=0.05)

    def test_failed_threshold_propagates_to_overall_status(self):
        result = analyze_environment(
            wind={
                'scenarios': [{'speed_mps': 10, 'weight': 1, 'exposure_factor': 1}],
                'receptors': [{'name': 'plaza', 'shelter_factor': 1}],
                'max_comfort_speed_mps': 5,
            }
        )
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(any(x['code'] == 'WIND_COMFORT_MAX_SPEED' and x['status'] == 'FAIL' for x in result['hard_results']))

    def test_invalid_solar_weights_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'total weight'):
            analyze_environment(solar={
                'surfaces': [{'area_m2': 10, 'tilt_deg': 0, 'azimuth_deg': 0}],
                'sun_samples': [{'altitude_deg': 30, 'azimuth_deg': 0, 'weight': 0}],
                'min_exposure_index': 0.1,
            })


if __name__ == '__main__':
    unittest.main()
