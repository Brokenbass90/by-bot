import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".."))
import ai_formula_v1 as F

OK = {"id": "AI_TEST_FORMULA", "semya": "AI_FORMULA_XS", "mehanizm": "x" * 70, "pochemu_ne_arbitrazhirovano": "y" * 40,
      "istochniki_dannyh": ["binance_klines_d1"], "priznak": "описание", "vremya_izvestnosti": "закрытие d−1", "napravlenie": "-",
      "gorizont": "1w", "vselennaya": "PIT топ-50 OI", "kontrol": "случайная монета", "falsifikaciya": "t ≤ 0",
      "ozhidaemaya_chastota_v_mesyac": 4, "izderzhki_ocenka_bps": 30, "formula": ["proizv", "m3_vsplesk", ["neg", "spot_minus_perp"]],
      "znak": -1, "okno": "W"}
S = {"okna": {"W": {"id": "W", "rol": "DEV", "nachalo": "2021-07-01", "konec": "2022-12-31", "alpha": 0.2, "byudzhet": 20},
              "C": {"id": "C", "rol": "CONFIRM", "nachalo": "2026-10-13", "konec": "2026-12-31"}}, "gipotezy": {}, "popytki": {}, "semi": {}}


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); F.ZHURNAL = Path(self.tmp.name) / "z.jsonl"

    def test_ok(self):
        self.assertEqual(F.proverit(OK, S), [])

    def test_chisla_zapreshcheny(self):
        e = F.proverit(dict(OK, formula=["minus", "m3_perp", 0.5]), S); self.assertTrue(any("числа" in x for x in e))

    def test_atom_i_operaciya_vne_slovarya(self):
        self.assertTrue(F.proverit(dict(OK, formula=["minus", "m3_perp", "rsi14"]), S))
        self.assertTrue(F.proverit(dict(OK, formula=["log", "m3_perp"]), S))

    def test_odinochnyy_atom_i_glubina(self):
        self.assertTrue(F.proverit(dict(OK, formula="m3_perp"), S))
        self.assertTrue(F.proverit(dict(OK, formula=["neg", ["neg", ["neg", ["neg", "m3_perp"]]]]), S))
        self.assertTrue(F.proverit(dict(OK, formula=["plus", ["minus", "m3_perp", "spot"], ["minus", "vyhodnye", "m3_vsplesk"]]), S))

    def test_pokrytie_okna(self):
        e = F.proverit(dict(OK, formula=["minus", "cb_premiya", "m3_perp"]), S); self.assertTrue(any("без данных" in x for x in e))

    def test_tolko_dev(self):
        self.assertTrue(any("DEV" in x for x in F.proverit(dict(OK, okno="C"), S)))

    def test_kanon_i_dubl(self):
        self.assertEqual(F.kanon(["plus", "spot", "m3_perp"]), F.kanon(["plus", "m3_perp", "spot"]))
        self.assertNotEqual(F.kanon(["minus", "spot", "m3_perp"]), F.kanon(["minus", "m3_perp", "spot"]))
        F.ZHURNAL.write_text(json.dumps({"shag": "zapusk", "formula": F.kanon(OK["formula"]), "kogda": "2020-01-01"}) + "\n")
        self.assertTrue(any("уже проверялась" in x for x in F.proverit(OK, S)))

    def test_rezerv_okna(self):
        S2 = json.loads(json.dumps(S)); S2["popytki"] = {f"p{i}": {"okno": "W"} for i in range(15)}
        self.assertTrue(any("резерв" in x for x in F.proverit(OK, S2)))
        S2["popytki"] = {f"p{i}": {"okno": "W"} for i in range(14)}
        self.assertEqual(F.proverit(OK, S2), [])

    def test_byudzhet_sutok(self):
        self.assertTrue(any("бюджет" in x for x in F.proverit(OK, S, segodnya_popytok=F.MAKS_POPYTOK_V_SUTKI)))

    def test_zapreshchennye_polya_kontrakta(self):
        self.assertTrue(F.proverit(dict(OK, porog=2.0), S))

    def test_vychislenie(self):
        D = {}
        def priznak(a, D):
            tab = {"m3_vsplesk": {"X": 0.1}, "spot_minus_perp": {"X": -0.3}}
            return lambda s, v: tab[a].get(s)
        g = F.funkciya(OK["formula"], D, priznak)
        self.assertAlmostEqual(g("X", "2022-01-01"), 0.1 * 0.3); self.assertIsNone(g("Y", "2022-01-01"))


if __name__ == "__main__":
    unittest.main()
