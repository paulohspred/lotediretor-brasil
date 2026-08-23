import sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services'/'solar-engine'/'app'))
from domain import SolarFinancialInput, financial_projection, fit_panels, normalize_distribution

class SolarDomainTests(unittest.TestCase):
    def test_distribution_normalizes(self):
        d=normalize_distribution([1]*12)
        self.assertEqual(len(d),12)
        self.assertAlmostEqual(sum(d),1.0,places=10)
    def test_distribution_rejects_bad_shape(self):
        with self.assertRaises(ValueError): normalize_distribution([1,2])
    def test_fit_panels_never_exceeds_packed_area(self):
        r=fit_panels(100,1,2,0.8)
        self.assertEqual(r['max_panels'],40)
        self.assertLessEqual(r['max_panels']*r['panel_area_m2'],r['usable_after_packing_m2'])
    def test_financial_projection_payback_and_npv(self):
        r=financial_projection(SolarFinancialInput(annual_kwh=10000,tariff_brl_per_kwh=1,capex_brl=20000,years=10,discount_rate=0.1,annual_tariff_escalation=0,annual_degradation=0))
        self.assertEqual(r['simple_payback_year'],2)
        self.assertGreater(r['npv_brl'],0)
        self.assertGreater(r['lcoe_brl_per_kwh'],0)

if __name__=='__main__': unittest.main()
