"""Тесты хука ai_generaciya: отсрочка, лимиты, квота, идемпотентность после рестарта, недоступная Ollama."""
import datetime as dt, json, shutil, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_generaciya as G
T0 = dt.datetime(2026, 10, 20, 8, 0, tzinfo=dt.timezone.utc)
OK_R = lambda: dict(segodnya=0, sutochnyy=3, ostalos=7, rezerv=5, menyu=27)


class T(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()); self.sv = (G.SOST, G.ZH)
        G.SOST = self.d / "s.json"; G.ZH = self.d / "z.jsonl"; self.vyzovy = 0

    def tearDown(self):
        G.SOST, G.ZH = self.sv; shutil.rmtree(self.d)

    def zap(self, otvet):
        def f():
            self.vyzovy += 1; return otvet
        return f

    def test_uspeh_odin_raz_v_sutki_i_posle_restarta(self):
        z = self.zap("V_OCHEREDI_HUKA"); self.assertEqual(G.prohod(T0, OK_R, z)["status"], "v_ocheredi")
        self.assertEqual(G.prohod(T0 + dt.timedelta(hours=1), OK_R, z)["status"], "uzhe_segodnya")
        self.assertEqual(self.vyzovy, 1)                       # состояние на диске → «рестарт» сторожа не повторяет

    def test_otsrochka_i_limit(self):
        z = self.zap("ОТКАЗ: давление памяти macOS = 2")
        self.assertEqual(G.prohod(T0, OK_R, z)["status"], "skip_resursy")
        self.assertEqual(G.prohod(T0 + dt.timedelta(minutes=30), OK_R, z)["status"], "otsrochka")
        t = T0
        for _ in range(6):
            t += dt.timedelta(hours=9); G.prohod(t.replace(day=20, hour=min(t.hour, 23)), OK_R, z)
        self.assertLessEqual(self.vyzovy, G.MAKS_POPYTOK_DEN)

    def test_ollama_nedostupna_ne_uspeh(self):
        r = G.prohod(T0, OK_R, self.zap("ОТКАЗ: Ollama недоступна: Connection refused"))
        self.assertEqual(r["status"], "skip_ollama"); self.assertIn("sleduyushchaya", r)

    def test_byudzhety_bez_zapuska(self):
        z = self.zap("V_OCHEREDI_HUKA")
        self.assertEqual(G.prohod(T0, lambda: dict(OK_R(), ostalos=5), z)["status"], "okonnyy_byudzhet_II_ischerpan")
        self.assertEqual(G.prohod(T0, lambda: dict(OK_R(), segodnya=3), z)["status"], "sutochnyy_byudzhet_reestra")
        self.assertEqual(self.vyzovy, 0)

    def test_nedelnaya_kvota(self):
        z = self.zap("V_OCHEREDI_HUKA"); t = dt.datetime(2026, 10, 19, 8, 0, tzinfo=dt.timezone.utc)   # понедельник
        st = [G.prohod(t + dt.timedelta(days=i), OK_R, z)["status"] for i in range(7)]
        self.assertEqual(st.count("v_ocheredi"), G.MAKS_V_NEDELYU); self.assertIn("nedelnaya_kvota", st)

    def test_zhurnal_dopisyvaetsya(self):
        G.prohod(T0, OK_R, self.zap("ОТКАЗ: x")); G.prohod(T0 + dt.timedelta(hours=2), OK_R, self.zap("V_OCHEREDI_HUKA"))
        z = [json.loads(s) for s in G.ZH.read_text().splitlines()]
        self.assertEqual([x["status"] for x in z], ["skip_resursy", "v_ocheredi"])


if __name__ == "__main__":
    unittest.main()
