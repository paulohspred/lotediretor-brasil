import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services'/'solar-engine'/'app'))
from domain import RectObstacle,pack_rectangular_surface,monthly_energy_balance

class SolarV18Tests(unittest.TestCase):
    def test_layout_respects_obstacle(self):
        r=pack_rectangular_surface(10,8,1,2,'PORTRAIT',0,0,None,0,[RectObstacle(4,2,2,2,0)])
        self.assertGreater(r['panel_count'],0)
        for p in r['panels']:
            overlap=not (p['x_m']+p['width_m']<=4 or 6<=p['x_m'] or p['y_m']+p['height_m']<=2 or 4<=p['y_m'])
            self.assertFalse(overlap)
    def test_auto_orientation_is_deterministic(self):
        a=pack_rectangular_surface(5,4,1.1,2,'AUTO',0.2,0.02)
        b=pack_rectangular_surface(5,4,1.1,2,'AUTO',0.2,0.02)
        self.assertEqual(a,b)
    def test_energy_balance_conserves_energy(self):
        c=[100]*12;g=[80]*6+[120]*6
        r=monthly_energy_balance(c,g)
        for i in range(12):
            self.assertAlmostEqual(r['self_consumption_monthly_kwh'][i]+r['grid_purchase_monthly_kwh'][i],c[i])
            self.assertAlmostEqual(r['self_consumption_monthly_kwh'][i]+r['injected_monthly_kwh'][i],g[i])
        self.assertGreater(r['self_consumption_ratio'],0)
if __name__=='__main__':unittest.main()
