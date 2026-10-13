import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import data_qa_v1 as Q


class TestDataQA(unittest.TestCase):
    def test_edinicy(self):
        self.assertEqual(Q.edinicy([1791905420755]), "ms")
        self.assertEqual(Q.edinicy([1735689600000000]), "us")      # спот Binance 2025+
        self.assertEqual(Q.edinicy([1791905420]), "s")

    def test_ryad_ловит_дубли_двойного_процесса(self):
        ts = [0, 300000, 600000, 300000, 600000, 900000]           # блок дописан дважды
        r = Q.ryad(ts, Q.M5)
        self.assertEqual(r["dubley"], 2); self.assertEqual(r["nazad"], 1)
        self.assertEqual(Q.ryad([0, 300000, 1200000], Q.M5)["dyr"], 1)
        self.assertEqual(Q.ryad([0, 300000, 600000], Q.M5), dict(dubley=0, nazad=0, dyr=0))

    def test_storona_perevernuta(self):
        bary = {i: (100, 101) for i in range(40)}                  # все бары роста
        plohie = {i: (60_000, 0) for i in range(40)}               # 'long' на росте — как у старого сборщика
        horoshie = {i: (0, 60_000) for i in range(40)}
        self.assertEqual(Q.storona_protiv_ceny(plohie, bary)["status"], "SIDE_INVERTED")
        self.assertEqual(Q.storona_protiv_ceny(horoshie, bary)["status"], "OK")
        self.assertEqual(Q.storona_protiv_ceny({1: (60_000, 0)}, bary)["status"], "MALO")

    def test_sostavnoy_kluch(self):
        d = Path(tempfile.mkdtemp()); f = d / "ish.jsonl"
        f.write_text("\n".join(json.dumps({"id": "a", "dvigatel": g, "ts": 1791905420755, "R": 0.1}) for g in ("CONTROL", "24H", "WIDE")) + "\n")
        old = Q.D; Q.D = d
        try: r = Q.q_ishody(dict(fayl="ish.jsonl", kluch=("id", "dvigatel")))
        finally: Q.D = old
        self.assertEqual(r["status"], "OK")

    def test_hvost(self):
        p = Path(tempfile.mkdtemp()) / "x.jsonl"
        p.write_text("".join(json.dumps({"i": i}) + "\n" for i in range(1000)))
        self.assertEqual([r["i"] for r in Q.hvost(p, 3)], [997, 998, 999])

    def test_ishody_vyrozhdennye(self):
        d = Path(tempfile.mkdtemp()); f = d / "ish.jsonl"
        f.write_text("\n".join(json.dumps(r) for r in [
            {"id": "a", "ts": 1791905420755, "R": 0.5}, {"id": "a", "ts": 1791905420755, "R": 373.0},
            {"id": "b", "ts": 1791905420755, "R": 0.1, "plecho": 6068}]) + "\n")
        old = Q.D; Q.D = d
        try: r = Q.q_ishody(dict(fayl="ish.jsonl"))
        finally: Q.D = old
        self.assertEqual(r["status"], "DEFEKT"); self.assertEqual(r["R_vyrozhdennyh"], 1)
        self.assertEqual(r["dubley_id"], 1); self.assertEqual(r["plecho_bolshe_100"], 1)


if __name__ == "__main__":
    unittest.main()
