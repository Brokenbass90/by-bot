"""Тесты хуков alpaca_h2b_zhurnal и alpaca_ii_veto_ten на копии реальной поставки 2026-10-16 (во временной папке)."""
import hashlib, json, shutil, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import alpaca_h2b_zhurnal as H
import alpaca_ii_veto_ten as V
REAL = HERE.parent / "data" / "alpaca_monthly58_daily_v1"
SES = "2026-10-16"


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Baza(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp()); self.src = self.t / "src"; self.src.mkdir()
        for x in (f"{SES}.json", f"{SES}.diagnostic.json", f"{SES}.delivery.json"):
            shutil.copy(REAL / x, self.src / x)
        self.sv = (H.SRC, H.ZH, V.SRC, V.ZH, V.KLIENT_TEST)
        H.SRC = V.SRC = self.src; H.ZH = self.t / "h2b.jsonl"; V.ZH = self.t / "veto.jsonl"

    def tearDown(self):
        H.SRC, H.ZH, V.SRC, V.ZH, V.KLIENT_TEST = self.sv; shutil.rmtree(self.t)

    def perepechatat(self, diag_fn):
        g = self.src / f"{SES}.diagnostic.json"; d = json.loads(g.read_text()); diag_fn(d); g.write_text(json.dumps(d))
        p = self.src / f"{SES}.delivery.json"; pe = json.loads(p.read_text()); pe["files"][g.name] = sha(g); p.write_text(json.dumps(pe))


class TestH2b(Baza):
    def test_dopisyvanie_i_dedup(self):
        r1 = H.prohod(); r2 = H.prohod()
        self.assertEqual(r1["novyh"], 1); self.assertEqual(r2["novyh"], 0)
        z = [json.loads(s) for s in H.ZH.read_text().splitlines()]
        self.assertEqual(len(z), 1); self.assertIn(z[0]["klass"], ("FORWARD", "BACKFILLED_DIAGNOSTIC"))
        self.assertIn("alpaca_honest_portfolio", z[0]["kod"]); self.assertEqual(len(z[0]["bumagi"]), 57)

    def test_podmena_fayla(self):
        f = self.src / f"{SES}.json"; d = json.loads(f.read_text()); d["session_date"] = SES; f.write_text(json.dumps(d) + " ")
        r = H.prohod(); self.assertEqual(r["oshibok"], 1)

    def test_propuski(self):
        H.prohod(); self.assertEqual(H.propuski(), [])


class TestVeto(Baza):
    def test_ne_mesyachnaya_sessiya(self):
        self.assertEqual(V.prohod()["resheniy"], 0); self.assertFalse(V.ZH.exists())

    def test_mesyachnaya_s_klientom_i_dedup(self):
        self.perepechatat(lambda d: d.__setitem__("monthly_calendar_due", True))
        V.KLIENT_TEST = lambda s, z: {"reshenie": "VETO", "prichina": "тест", "faktory": ["a"]}
        r = V.prohod(); self.assertEqual(r["resheniy"], 5); self.assertEqual(r["otvety"], ["VETO"])
        self.assertEqual(V.prohod()["resheniy"], 0)
        z = [json.loads(s) for s in V.ZH.read_text().splitlines()]
        for x in z:
            for k in ("decision_id", "tiker", "prompt_sha", "vhod_sha", "istochnik_sha", "market_data_asof", "novosti",
                      "ocenka_otbora", "v_vybore_monthly", "otvet", "prichina", "otvet_utc", "do_otkrytiya_vhoda"):
                self.assertIn(k, x)
        self.assertEqual(sorted(x["tiker"] for x in z if x["v_vybore_monthly"]), ["ABBV", "ADSK", "MSFT", "SHOP"])

    def test_ollama_nedostupna_ne_veto(self):
        self.perepechatat(lambda d: d.__setitem__("monthly_calendar_due", True))
        out = V.reshenie(SES)          # в тестовой среде Ollama нет
        self.assertTrue(all(z["otvet"] == "MISSING" for z in out))

    def test_paritet(self):
        def isk(d):
            d["monthly_calendar_due"] = True
            for x in d["stocks"]:
                if x.get("candidate_pass"): x["candidate_score"] += 0.01; break
        self.perepechatat(isk); V.KLIENT_TEST = lambda s, z: {"reshenie": "APPROVE"}
        out = V.reshenie(SES); self.assertEqual(out[0]["status"], "PARITY_FAIL")

    def test_net_buduschego_vo_vhode(self):
        d, g, _, _ = V.postavka(SES)[0]
        k, ih, vybor, par, R = V.kandidaty(d, g)
        for s in k:
            self.assertLessEqual(V.vhod_ii(s, R, {x["symbol"]: x for x in g["stocks"]}[s], g["spy_gate"])["sessiya"], SES)


if __name__ == "__main__":
    unittest.main()
