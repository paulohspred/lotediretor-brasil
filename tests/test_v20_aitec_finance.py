from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'aitec-engine' / 'app'))

from finance_solver import FINANCE_SOLVER_VERSION, calculate_project_finance  # noqa: E402


UNITS = [
    {'name': '2D', 'count': 10, 'saleable_area_m2': 50, 'price_per_m2': 10000},
    {'name': '3D', 'count': 5, 'saleable_area_m2': 80, 'price_per_m2': 12000},
]


class FinanceV20Tests(unittest.TestCase):
    def test_reproducible_vgv_capex_margin_and_cashflow(self):
        result = calculate_project_finance(
            UNITS,
            construction_area_m2=1500,
            land_cost=1_000_000,
            hard_cost_per_m2=3000,
            soft_cost_percent_of_hard=10,
            contingency_percent_of_hard_soft=5,
            taxes_percent_of_vgv=4,
            sales_commission_percent_of_vgv=5,
            market_snapshot_id='market:sao-paulo:2026-08',
            cost_snapshot_id='cost:sinduscon:2026-08',
            other_capex=100_000,
            cash_flows=[{'month': 0, 'amount': -5_000_000}, {'month': 12, 'amount': 7_000_000}],
            annual_discount_rate_percent=10,
            min_margin_percent=20,
        )
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['solver_version'], FINANCE_SOLVER_VERSION)
        self.assertEqual(result['vgv'], 9_800_000)
        self.assertEqual(result['capex']['hard_cost'], 4_500_000)
        self.assertGreater(result['profit'], 0)
        self.assertGreater(result['margin_percent'], 20)
        self.assertEqual(result['cashflow']['status'], 'CALCULATED')
        self.assertIsNotNone(result['cashflow']['npv'])
        self.assertIsNotNone(result['cashflow']['irr_annual_percent'])
        self.assertEqual(result['provenance']['market_snapshot_id'], 'market:sao-paulo:2026-08')
        self.assertEqual(result['pareto_metrics']['vgv'], result['vgv'])

    def test_failed_margin_is_not_hidden(self):
        result = calculate_project_finance(
            UNITS,
            construction_area_m2=1500,
            land_cost=8_000_000,
            hard_cost_per_m2=4000,
            soft_cost_percent_of_hard=15,
            contingency_percent_of_hard_soft=10,
            taxes_percent_of_vgv=5,
            sales_commission_percent_of_vgv=6,
            market_snapshot_id='market-1',
            cost_snapshot_id='cost-1',
            min_margin_percent=15,
        )
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(any(x['code'] == 'MIN_PROJECT_MARGIN' and x['status'] == 'FAIL' for x in result['hard_results']))

    def test_without_acceptance_thresholds_result_is_calculated_not_pass(self):
        result = calculate_project_finance(
            UNITS,
            construction_area_m2=1200,
            land_cost=500_000,
            hard_cost_per_m2=2500,
            soft_cost_percent_of_hard=10,
            contingency_percent_of_hard_soft=5,
            taxes_percent_of_vgv=4,
            sales_commission_percent_of_vgv=5,
            market_snapshot_id='market-1',
            cost_snapshot_id='cost-1',
        )
        self.assertEqual(result['status'], 'CALCULATED')
        self.assertEqual(result['hard_results'], [])

    def test_missing_market_or_cost_provenance_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            calculate_project_finance(
                UNITS,
                construction_area_m2=1200,
                land_cost=500_000,
                hard_cost_per_m2=2500,
                soft_cost_percent_of_hard=10,
                contingency_percent_of_hard_soft=5,
                taxes_percent_of_vgv=4,
                sales_commission_percent_of_vgv=5,
                market_snapshot_id='',
                cost_snapshot_id='cost-1',
            )

    def test_price_is_never_invented(self):
        with self.assertRaisesRegex(ValueError, 'requires explicit'):
            calculate_project_finance(
                [{'name': 'X', 'count': 1, 'saleable_area_m2': 50}],
                construction_area_m2=100,
                land_cost=0,
                hard_cost_per_m2=1,
                soft_cost_percent_of_hard=0,
                contingency_percent_of_hard_soft=0,
                taxes_percent_of_vgv=0,
                sales_commission_percent_of_vgv=0,
                market_snapshot_id='market-1',
                cost_snapshot_id='cost-1',
            )


if __name__ == '__main__':
    unittest.main()
