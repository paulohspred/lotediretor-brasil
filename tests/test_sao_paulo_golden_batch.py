import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'workers' / 'data-pipelines'))

from sao_paulo_golden_candidates_batch import select_batch  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = json.dumps(payload, sort_keys=True).encode('utf-8')

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class SaoPauloGoldenBatchTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((ROOT / 'data' / 'municipality-labs' / 'sao-paulo-3550308.json').read_text(encoding='utf-8'))
        _, dataset = next(
            (source, dataset)
            for source in self.profile['sources']
            for dataset in source.get('datasets', [])
            if dataset.get('code') == 'PARCEL'
        )
        mapping = dataset['canonical_mapping']
        self.id_field = mapping['official_identifier_field']
        self.area_field = mapping.get('land_area_m2_field')
        self.street_field = mapping.get('street_name_field')
        self.number_field = mapping.get('street_number_field')

    def feature(self, index):
        props = {self.id_field: f'OFFICIAL-{index:03d}'}
        if self.area_field:
            props[self.area_field] = 200 + index
        if self.street_field:
            props[self.street_field] = f'Rua {index}'
        if self.number_field:
            props[self.number_field] = str(index)
        x = -46.70 + index * 0.001
        y = -23.60 + index * 0.001
        return {
            'type': 'Feature',
            'properties': props,
            'geometry': {
                'type': 'Polygon',
                'coordinates': [[[x, y], [x + 0.0005, y], [x + 0.0005, y + 0.0005], [x, y + 0.0005], [x, y]]],
            },
        }

    def test_batch_uses_one_bounded_official_request_and_never_invents_legal_truth(self):
        payload = {'type': 'FeatureCollection', 'numberMatched': 100000, 'features': [self.feature(i) for i in range(20)]}
        with patch('sao_paulo_golden_candidates_batch.requests.get', return_value=FakeResponse(payload)) as get:
            result = select_batch(copy.deepcopy(self.profile), 20, '2026-08-24', timeout=20)

        self.assertEqual(get.call_count, 1)
        params = get.call_args.kwargs['params']
        self.assertEqual(params['count'], 20)
        self.assertEqual(params['startIndex'], 0)
        self.assertIn(self.id_field, params['sortBy'])
        self.assertEqual(result['selection']['strategy'], 'stable_sorted_prefix_single_wfs_page')
        self.assertFalse(result['selection']['representative_sampling_claimed'])
        self.assertEqual(len(result['candidates']), 20)
        self.assertTrue(all(case['expected_zone_code'] is None for case in result['candidates']))
        self.assertTrue(all(case['expected_parameters'] == {} for case in result['candidates']))
        self.assertTrue(all(case['status'] == 'PENDING_HUMAN_REVIEW' for case in result['candidates']))

    def test_batch_rejects_partial_live_page(self):
        payload = {'type': 'FeatureCollection', 'features': [self.feature(i) for i in range(9)]}
        with patch('sao_paulo_golden_candidates_batch.requests.get', return_value=FakeResponse(payload)):
            with self.assertRaisesRegex(RuntimeError, 'wfs_batch_returned_too_few_features'):
                select_batch(copy.deepcopy(self.profile), 10, '2026-08-24', timeout=20)


if __name__ == '__main__':
    unittest.main()
