import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pump4_polnyy_povtor as P
G = P.GRAN_VPERED


class T(unittest.TestCase):
    def test_tolko_dopisyvaet_i_lovit_reviziyu(self):
        f = Path(tempfile.mkdtemp()) / "z.jsonl"
        s1 = [dict(sym="A", ts=G - 3600000, side="short", status="ZAKRYTA", R=0.1),          # история — не пишется
              dict(sym="B", ts=G + 3600000, side="short", status="OTKRYTA")]
        self.assertEqual(P.zhurnal_vpered(s1, G + 7200000, f), dict(novyh_signalov=1, novyh_ishodov=0, reviziy=0))
        s2 = [dict(sym="B", ts=G + 3600000, side="short", status="ZAKRYTA", R=0.3, ctrl=0.0)]
        self.assertEqual(P.zhurnal_vpered(s2, G + 9e6, f)["novyh_ishodov"], 1)
        pervye = f.read_text().splitlines()
        s3 = [dict(sym="B", ts=G + 3600000, side="short", status="ZAKRYTA", R=0.5, ctrl=0.0)]
        self.assertEqual(P.zhurnal_vpered(s3, G + 1e7, f)["reviziy"], 1)
        self.assertEqual(P.zhurnal_vpered([], G + 2e7, f)["reviziy"], 1)                       # исчез
        self.assertEqual(f.read_text().splitlines()[:len(pervye)], pervye)                     # прошлые строки не тронуты
        self.assertEqual(P.zhurnal_vpered(s3, G + 3e7, f)["reviziy"], 0)                       # ревизия не дублируется


if __name__ == "__main__":
    unittest.main()
