import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'workers' / 'data-pipelines'))

from municipality_golden_gate import evaluate  # noqa: E402
from sao_paulo_golden_candidates import deterministic_offsets, build_candidate  # noqa: E402


class SaoPauloGoldenGateTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((ROOT / 'data' / 'municipality-labs' / 'sao-paulo-3550308.json').read_text(encoding='utf-8'))
        self.plan = json.loads((ROOT / 'data' / 'municipality-labs' / 'sao-paulo-validation-plan.json').read_text(encoding='utf-8'))

    def reviewed_case(self, index: int):
        dimensions = {
            dimension: {'disposition': 'CONFIRMED', 'evidence_ref': f'evidence:{index}:{dimension}'}
            for dimension in self.plan['required_review_dimensions']
        }
        checks = {
            check: {'status': 'PASS', 'evidence_ref': f'evidence:{index}:check:{n}'}
            for n, check in enumerate(self.plan['acceptance_checks'])
        }
        return {
            'case_code': f'3550308-REVIEWED-{index:02d}',
            'input_kind': 'OFFICIAL_PARCEL_ID',
            'input_payload': {'official_parcel_id': f'parcel-{index}'},
            'base_date': '2026-08-23',
            'expected_official_reference': f'parcel-{index}',
            'expected_zone_code': 'REVIEWED_ZONE',
            'expected_parameters': {'reviewed': True},
            'human_reviewer': 'reviewer-id',
            'human_reviewed_at': '2026-08-23T20:00:00-03:00',
            'status': 'PASS',
            'evidence': {
                'parcel_snapshot_sha256': 'a' * 64,
                'zone_snapshot_sha256': 'b' * 64,
                'legal_snapshot_sha256': 'c' * 64,
                'analysis_run_id': f'analysis-{index}',
                'evidence_report_ref': f'report-{index}',
            },
            'review_dimensions': dimensions,
            'acceptance_checks': checks,
        }

    def test_repository_state_stays_fail_closed_until_real_reviews_exist(self):
        result = evaluate(self.profile, self.plan)
        self.assertEqual(result['status'], 'PENDING_CASE_SELECTION')
        self.assertFalse(result['homologation_eligible'])
        self.assertFalse(result['production_ready'])
        self.assertEqual(result['total_cases'], 0)

    def test_ten_complete_human_reviewed_cases_only_become_eligible_not_production_ready(self):
        plan = copy.deepcopy(self.plan)
        plan['cases'] = [self.reviewed_case(i) for i in range(10)]
        result = evaluate(self.profile, plan)
        self.assertEqual(result['status'], 'READY_FOR_PROFESSIONAL_HOMOLOGATION')
        self.assertTrue(result['homologation_eligible'])
        self.assertFalse(result['production_ready'])
        self.assertEqual(result['passing_cases'], 10)

    def test_missing_snapshot_evidence_blocks_ready_state(self):
        plan = copy.deepcopy(self.plan)
        plan['cases'] = [self.reviewed_case(i) for i in range(10)]
        plan['cases'][4]['evidence']['legal_snapshot_sha256'] = None
        result = evaluate(self.profile, plan)
        self.assertEqual(result['status'], 'BLOCKED_REVIEW')
        self.assertFalse(result['homologation_eligible'])
        self.assertTrue(any('legal_snapshot_sha256' in issue for issue in result['cases'][4]['issues']))

    def test_unknown_dimension_requires_rationale(self):
        plan = copy.deepcopy(self.plan)
        plan['cases'] = [self.reviewed_case(i) for i in range(10)]
        plan['cases'][0]['review_dimensions']['height'] = {'disposition': 'UNKNOWN'}
        result = evaluate(self.profile, plan)
        self.assertEqual(result['status'], 'BLOCKED_REVIEW')
        self.assertTrue(any('unknown_dimension_without_rationale:height' in issue for issue in result['cases'][0]['issues']))

    def test_candidate_offsets_are_deterministic_and_bounded(self):
        self.assertEqual(deterministic_offsets(100, 10), [5, 15, 25, 35, 45, 55, 65, 75, 85, 95])
        offsets = deterministic_offsets(7, 20)
        self.assertEqual(offsets, list(range(7)))

    def test_candidate_builder_never_invents_zone_or_parameters(self):
        source = {'code': 'SP_GEOSAMPA_WFS', 'authority': 'Prefeitura de São Paulo'}
        dataset = {
            'code': 'PARCEL',
            'typename': 'geoportal:lote_cidadao',
            'canonical_mapping': {
                'official_identifier_field': 'cd_identificador',
                'land_area_m2_field': 'qt_area_terreno',
                'street_name_field': 'nm_logradouro_completo',
                'street_number_field': 'cd_numero_porta',
            },
        }
        feature = {
            'properties': {
                'cd_identificador': 'OFFICIAL-1',
                'qt_area_terreno': 250,
                'nm_logradouro_completo': 'Rua de teste',
                'cd_numero_porta': '10',
            },
            'geometry': {
                'type': 'Polygon',
                'coordinates': [[[-46.64, -23.55], [-46.63, -23.55], [-46.63, -23.54], [-46.64, -23.54], [-46.64, -23.55]]],
            },
        }
        candidate = build_candidate(feature, dataset, source, 5, 'd' * 64, '2026-08-23')
        self.assertEqual(candidate['expected_official_reference'], 'OFFICIAL-1')
        self.assertIsNone(candidate['expected_zone_code'])
        self.assertEqual(candidate['expected_parameters'], {})
        self.assertEqual(candidate['status'], 'PENDING_HUMAN_REVIEW')


if __name__ == '__main__':
    unittest.main()
