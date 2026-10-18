import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reestr_v1 import Reestr, OshibkaReestra


class T(unittest.TestCase):
    def setUp(self):
        self.r = Reestr(Path(tempfile.mkdtemp()) / "r.jsonl")
        self.kw = dict(rynok="alpaca", ekonomika="ECONOMIC_PASS", ispolnenie="NE_PROVERENO", owner_go="нет",
                       dokazatelstva=["x.md"], parametry={"mest": 4})

    def test_zapis_i_versii(self):
        self.r.pasport("A", "v1", **self.kw); self.r.pasport("A", "v2", **dict(self.kw, ekonomika="ECONOMIC_FAIL"))
        S = self.r.sostoyanie(); self.assertEqual([p["versiya"] for p in S["pasporta"]["A"]], ["v1", "v2"])

    def test_obyazatelnye(self):
        with self.assertRaises(OshibkaReestra): self.r.pasport("A", "v1", **dict(self.kw, dokazatelstva=[]))
        with self.assertRaises(OshibkaReestra): self.r.pasport("A", "v1", **dict(self.kw, ekonomika="PASS"))

    def test_povtor_versii(self):
        self.r.pasport("A", "v1", **self.kw)
        with self.assertRaises(OshibkaReestra): self.r.pasport("A", "v1", **self.kw)
        self.r.pasport("A", "v1", obnovlenie_statusa=True, **dict(self.kw, ispolnenie="EXECUTION_PASS"))


if __name__ == "__main__":
    unittest.main()
