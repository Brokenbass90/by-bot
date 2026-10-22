import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import poly_yes_verdikt as V


def zhurnal(n_sob, dohod, dat=None):
    rows = []
    for i in range(n_sob):
        cid = f"c{i}"; d = f"2026-11-{(i % (dat or n_sob)) + 1:02d}"
        rows.append(dict(tip="reshenie", status="VHOD", conditionId=cid, sobytie=f"A{i}|{d}", raschet_ms=i))
        rows.append(dict(tip="ishod", status="OK", conditionId=cid, dohod=dohod(i), dohod_stress=dohod(i) - 0.01))
    return rows


class T(unittest.TestCase):
    def test_do_30_dohod_ne_chitaetsya(self):
        rows = zhurnal(29, lambda i: 0.0)
        for r in rows:
            if r['tip'] == 'ishod': r['dohod'] = r['dohod_stress'] = None   # если бы доход читался — упало бы
        o = V.sudit(rows); self.assertEqual(o["status"], "NAKOPLENIE"); self.assertNotIn("srednee", o)

    def test_pass_fail(self):
        self.assertEqual(V.sudit(zhurnal(40, lambda i: 0.2 if i % 3 else -0.1))["status"], "PASS")
        self.assertEqual(V.sudit(zhurnal(40, lambda i: -0.05 if i % 2 else 0.01))["status"], "FAIL")

    def test_klastery_po_datam(self):
        # тот же доход, но все события на 3 датах → t по датам мал → INCONCLUSIVE
        o = V.sudit(zhurnal(40, lambda i: 0.3 if i % 3 == 0 else -0.05, dat=3)); self.assertIn(o["status"], ("INCONCLUSIVE", "FAIL"))

    def test_nepolnoe_sobytie_ne_schitaetsya(self):
        rows = zhurnal(30, lambda i: 0.1); rows.append(dict(tip="reshenie", status="VHOD", conditionId="x", sobytie="A0|2026-11-01", raschet_ms=0))
        self.assertEqual(V.sudit(rows)["sobytiy_s_ishodom"], 29)


if __name__ == "__main__":
    unittest.main()
