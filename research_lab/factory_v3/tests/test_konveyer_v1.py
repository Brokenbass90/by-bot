import sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(HERE))
import konveyer_v1 as K                  # noqa: E402
from reestr_v1 import Reestr             # noqa: E402

KARTA = dict(data_ready=True, istochniki=["sintetika"], hist_dev="ferma", sobytiy_v_nedelyu=50, ozhidanie_vpered_dney=14,
             ispolnimost="ponyatna", put_k_micro_live="—", mehanizm="шум")


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.q = Path(self.d) / "q.jsonl"; self.r = Reestr(Path(self.d) / "r.jsonl")
        self.r.semya("S", "тест"); self.r.gipoteza("G", "S", "шум", ["sintetika"]); self.r.perehod("G", "SCREEN", "старт")
        self.r.okno("DEV1", "sintetika", "2021-01-01", "2023-12-31", "DEV", byudzhet=5)

    def spec(self, i):
        return dict(id=f"G_{i}", gipoteza="G", okno="DEV1", eksperiment="ferma_primery:moment_na_shume", parametry=dict(sym="S1", lookback=10, hold=2),
                    kriterii=dict(min_n=3, znak="+"))

    def test_karta_obyazatelna(self):
        with self.assertRaises(ValueError): K.podat(self.spec(1), dict(KARTA, sobytiy_v_nedelyu=None), self.q)
        with self.assertRaises(ValueError): K.podat(dict(self.spec(1), eksperiment="os:system"), KARTA, self.q)

    def test_odin_raz_i_blocked(self):
        K.podat(self.spec(1), KARTA, self.q); K.podat(self.spec(2), dict(KARTA, data_ready=False), self.q)
        it = K.prohod(self.q, reestr=self.r, processov=1)
        self.assertEqual({x["id"]: x["status"] for x in it}["G_2"], "BLOCKED_DATA")
        self.assertIn({x["id"]: x["status"] for x in it}["G_1"], ("PASS", "FAIL"))
        self.assertEqual(K.prohod(self.q, reestr=self.r, processov=1), [])


if __name__ == "__main__":
    unittest.main()
