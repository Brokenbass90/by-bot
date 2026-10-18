import json, tempfile, unittest
from pathlib import Path
import polymarket_stend as S

H = 3600


def fixture(d: Path):
    (d / "prices").mkdir()
    m = [
        # бинарный рынок, YES выиграл, закрыт в t=100H, план тоже 100H
        dict(id="A", question="a?", category="x", startDate=0, endDate=100 * H, closedTime=100 * H,
             outcomes='["Yes","No"]', clobTokenIds='["a1","a0"]', outcomePrices='["1","0"]'),
        # закрылся ДОСРОЧНО: план 200H, фактически 90H, NO выиграл
        dict(id="B", question="b?", category="x", startDate=0, endDate=200 * H, closedTime=90 * H,
             outcomes='["Yes","No"]', clobTokenIds='["b1","b0"]', outcomePrices='["0","1"]'),
        # отменён/неоднозначен
        dict(id="C", question="c?", category="y", startDate=0, endDate=100 * H, closedTime=100 * H,
             outcomes='["Yes","No"]', clobTokenIds='["c1","c0"]', outcomePrices='["0.5","0.5"]'),
    ]
    (d / "markets.jsonl").write_text("\n".join(json.dumps(x) for x in m))
    hist = {"a1": [(t * H, 0.85) for t in range(0, 100)], "a0": [(t * H, 0.15) for t in range(0, 100)],
            "b1": [(t * H, 0.90) for t in range(0, 90)], "b0": [(t * H, 0.10) for t in range(0, 90)],
            "c1": [(t * H, 0.50) for t in range(0, 100)], "c0": [(t * H, 0.50) for t in range(0, 100)]}
    for k, v in hist.items():
        (d / "prices" / f"{k}.json").write_text(json.dumps({"history": [{"t": a, "p": b} for a, b in v]}))


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); d = Path(self.tmp.name); fixture(d); self.R = S.zagruzit(d)

    def test_zagruzka(self):
        r = {x.id: x for x in self.R}
        self.assertEqual(r["A"].pobeditel, 0); self.assertEqual(r["B"].pobeditel, 1); self.assertIsNone(r["C"].pobeditel)
        self.assertEqual(r["B"].plan, 200 * H); self.assertEqual(r["B"].zakryt, 90 * H)

    def test_net_budushchih_cen(self):
        r = {x.id: x for x in self.R}["A"]
        self.assertEqual(S.Proshloe(self.R, 10 * H + 5).cena(r, 0), 0.85)
        self.assertIsNone(S.Proshloe(self.R, 100 * H).cena(r, 0))      # закрыт — цены нет
        self.assertIsNone(S.Proshloe(self.R, -1).cena(r, 0))           # ещё не открыт

    def test_dosrochnoe_zakrytie_ne_vidno(self):
        """В 80H стратегия не должна знать, что B закроется в 90H: до планового закрытия 120 ч, «за сутки» не берём."""
        st = S.favorit_za_sutki(S.Proshloe(self.R, 80 * H))          # A: 20 ч до плана → да; B: 120 ч → нет
        self.assertEqual([s.rynok_id for s in st], ["A"])
        st = S.favorit_za_sutki(S.Proshloe(self.R, 70 * H))          # A: 30 ч → нет
        self.assertEqual([s.rynok_id for s in st], [])

    def test_raschet_i_izderzhki(self):
        z = S.progon(self.R, S.favorit_za_sutki, [77 * H], S.Izderzhki(0.01, 0.0))
        self.assertEqual(z["n"], 1); self.assertAlmostEqual(z["sdelki"][0]["dohod"], 1 / 0.86 - 1)

    def test_zaglyadyvanie_lovitsya(self):
        plohaya = lambda okno: [S.Stavka("A", 0, 0.85, okno.T + 1)]
        with self.assertRaises(RuntimeError):
            S.progon(self.R, plohaya, [10 * H], S.Izderzhki())

    def test_kalibrovka(self):
        k = S.kalibrovka(self.R, 24 * H)
        b = [x for x in k if x["n"]]
        self.assertEqual(sum(x["n"] for x in b), 2)          # A и B; C неоднозначен


if __name__ == "__main__":
    unittest.main()
