import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import liq_v2_1_konveyer as K

H = K.H


def z(sym, ts, side, usd, lag=1000, sha=None, clock="RECEIVE_OBSERVED", man=K.EPOHA_MANIFEST):
    return dict(symbol=sym, ts_ms=ts, t_available_ms=ts + lag, side=side, usd=usd, causal_clock_status=clock,
                raw_item_canonical_sha256=sha or f"{sym}{ts}{side}{usd}", source_manifest_sha256=man)


class T(unittest.TestCase):
    h = (K.EPOHA_START_MS // H * H + H) + K.PROGREV + 5 * H

    def test_sobytie_i_prichinnost(self):
        zap = [z("AUSDT", self.h + 10, "long", 60_000)]
        sob, _ = K.sobytiya(zap, self.h + 3 * H)
        self.assertEqual([(e["tip"], e["storona"]) for e in sob], [("LONG_LIQ", 1)])
        self.assertEqual(sob[0]["reshenie_ms"], self.h + H + 2 * K.MIN)
        pozdno = [z("AUSDT", self.h + 10, "long", 60_000, lag=H + 5 * K.MIN)]
        self.assertEqual(K.sobytiya(pozdno, self.h + 3 * H)[0], [])          # не успело к решению

    def test_porogi(self):
        self.assertEqual(K.sobytiya([z("AUSDT", self.h, "long", 49_000)], self.h + 3 * H)[0], [])
        self.assertEqual(K.sobytiya([z("AUSDT", self.h, "long", 60_000), z("AUSDT", self.h + 1, "short", 30_000)], self.h + 3 * H)[0], [])

    def test_progrev(self):
        rano = K.EPOHA_START_MS // H * H + 2 * H
        self.assertEqual(K.sobytiya([z("AUSDT", rano, "long", 1e6)], rano + 3 * H)[0], [])

    def test_dubli_i_epoha(self, tmp=Path("/tmp")):
        import json, tempfile
        a = z("AUSDT", self.h, "long", 60_000, sha="x"); b = dict(a); c = z("BUSDT", self.h, "long", 1, man="drugaya")
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            for r in (a, b, c): f.write(json.dumps(r) + "\n")
        zap, dubl, ch = K.zagruzit([f.name])
        self.assertEqual((len(zap), dubl, ch), (1, 1, 1))

    def test_unknown_isklyuchaetsya(self):
        self.assertEqual(K.sobytiya([z("AUSDT", self.h, "long", 1e6, clock="UNKNOWN_SKEW")], self.h + 3 * H)[0], [])

    def test_vorota(self):
        self.assertEqual(K.vorota([], dict(dolya_pozdnih=0.0))["status"], "NOT_YET")
        self.assertEqual(K.vorota([], dict(dolya_pozdnih=0.2))["status"], "FAIL_QA")


if __name__ == "__main__":
    unittest.main()
