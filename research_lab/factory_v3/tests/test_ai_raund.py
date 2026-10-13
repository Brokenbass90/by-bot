import hashlib, json, sys, tempfile, threading, time, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_raund as R
from tests.test_ai_kontrakt_v1 import HOROSHEE

GB = 2**30


class Fake(BaseHTTPRequestHandler):
    sost = {}
    def log_message(self, *a): pass
    def _otvet(self, obj):
        b = json.dumps(obj).encode(); self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        s = Fake.sost
        if self.path == "/api/tags": self._otvet(dict(models=[dict(name=n, size=g * GB) for n, g in s["tags"].items()]))
        elif self.path == "/api/ps": self._otvet(dict(models=[dict(name=n) for n in s["ps"]]))
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.sost["zaprosy"].append(body)
        if body.get("prompt") == "": return self._otvet(dict(response="", done=True))       # выгрузка
        time.sleep(Fake.sost.get("zaderzhka", 0))
        self._otvet(dict(response=json.dumps(HOROSHEE), done=True))


class TestAIRaund(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.host = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()

    def setUp(self):
        Fake.sost = dict(tags={"qwen3:8b": 5.2, "qwen3:32b": 20.0, "llama3:8b": 4.7}, ps=[], zaprosy=[], zaderzhka=0)
        d = Path(tempfile.mkdtemp()); R.LOCKS = d / "locks"
        self.reestr = d / "reestr.jsonl"; self.reestr.write_text(""); R.PUT_PO_UMOLCHANIYU = self.reestr

    def run_(self, *args, pamyat=24.0):
        return R.main(["--host", self.host, *args], pamyat_fn=lambda: pamyat)

    def gen(self): return [z for z in Fake.sost["zaprosy"] if z.get("prompt") != ""]

    def test_otkazy_bez_inferensa(self):
        self.assertEqual(self.run_("--model", "llama3:8b"), 2)                  # не в списке
        self.assertEqual(self.run_("--model", "qwen3:32b"), 2)                  # не в списке и > 6 ГБ
        Fake.sost["ps"] = ["qwen3:8b"]; self.assertEqual(self.run_(), 2)        # уже загружена
        Fake.sost["ps"] = []
        self.assertEqual(self.run_(pamyat=7.0), 2)                              # 7 < 5.2 + 4
        self.assertEqual(self.run_(pamyat=None), 2)                             # память не измерена → fail-closed
        self.assertEqual(self.run_("--n", "9"), 2)
        self.assertEqual(self.gen(), [])

    def test_proverka_ne_gruzit_model(self):
        self.assertEqual(self.run_("--proverka"), 0); self.assertEqual(Fake.sost["zaprosy"], [])

    def test_suhoy_ogranichen_i_read_only(self):
        h0 = hashlib.sha256(self.reestr.read_bytes()).hexdigest()
        self.assertEqual(self.run_(), 0)
        g = self.gen(); self.assertEqual(len(g), 1)
        o = g[0]["options"]
        self.assertEqual((o["num_ctx"], o["num_predict"], o["num_thread"]), (2048, 512, 4))
        self.assertIs(g[0]["think"], False); self.assertEqual(g[0]["keep_alive"], 0)
        self.assertLess(len(g[0]["system"]), 6000)
        self.assertEqual(Fake.sost["zaprosy"][-1]["prompt"], "")                # выгрузка в конце
        self.assertEqual(hashlib.sha256(self.reestr.read_bytes()).hexdigest(), h0)

    def test_taymaut_ogranichen(self):
        Fake.sost["zaderzhka"] = 3; R.TIMEOUT_S = 1
        try:
            t0 = time.time(); self.assertEqual(self.run_(), 0); self.assertLess(time.time() - t0, 6)
        finally: R.TIMEOUT_S = 120
        self.assertEqual(Fake.sost["zaprosy"][-1]["prompt"], "")                # модель выгружена и после таймаута

    def test_odin_raund_odnovremenno(self):
        fd = R.zamok()
        with self.assertRaises(R.Otkaz): R.zamok()


if __name__ == "__main__":
    unittest.main()
