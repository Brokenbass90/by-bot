"""Сквозной пример BRAIN_V3 (26.10.2026): сигнал PUMP4 из журнала вперёд → возможность → решения пар V3 (V1 по PUMP4 не решают)
→ исход → решение после исхода запрещено. Плюс устаревший сигнал (обнаружен > 6 ч) — не причинный, риск не занимает."""
import hashlib, json, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(HERE))
import opportunity_v2 as V2, brain_shadow_v1 as B   # noqa: E402
H = 3_600_000; T0 = 1793005200000 + 10 * H


def stroka(**z):
    z["sha256"] = hashlib.sha256(json.dumps(z, sort_keys=True).encode()).hexdigest(); return json.dumps(z) + "\n"


class T(unittest.TestCase):
    def test_skvoznoy(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); B.D = d; (d / "kity_bybit_ten").mkdir()
            zh = d / "pump4_vpered_zhurnal.jsonl"
            zh.write_text(stroka(vid="SIGNAL", sym="AUSDT", ts=T0, side="short", status="OTKRYTA", uvideno_ms=T0 + 3 * H, zapazdyvanie_ch=3.0)
                          + stroka(vid="SIGNAL", sym="BUSDT", ts=T0, side="short", status="OTKRYTA", uvideno_ms=T0 + 20 * H, zapazdyvanie_ch=20.0))
            hr = V2.Hranilishche(d / "brain")
            r = B._prohod(hr, btc=[], seychas=T0 + 3 * H + 60_000)
            self.assertEqual(r["novyh"], 2)
            dec = {(x["opp_id"], x["policy"]): x for x in hr.dec.zapisi}
            pol = {p for _, p in dec}
            self.assertEqual(pol, {"BASELINE_V3", "BRAIN_V3"})                      # V1/V2 по PUMP4 не решают
            a = next(o for o in hr.opp.zapisi if o["symbol"] == "AUSDT"); b = next(o for o in hr.opp.zapisi if o["symbol"] == "BUSDT")
            self.assertEqual(dec[(a["opp_id"], "BASELINE_V3")]["allocation_units"], 1.0)   # фиксированное распределение
            self.assertEqual(dec[(a["opp_id"], "BRAIN_V3")]["allocation_units"], 0.0)      # фандинг UNKNOWN → CASH
            self.assertIn("unknown_edge", dec[(a["opp_id"], "BRAIN_V3")]["constraints"])
            self.assertIn("ne_prichinno", dec[(b["opp_id"], "BASELINE_V3")]["constraints"])  # обнаружен через 20 ч
            with zh.open("a") as f:
                f.write(stroka(vid="ISHOD", sym="AUSDT", ts=T0, R=0.3, ctrl=0.0, komissiya_R=0.01, risk_pct=15.0, uvideno_ms=T0 + 50 * H))
            r2 = B._prohod(hr, btc=[], seychas=T0 + 50 * H)
            self.assertEqual(r2["ishodov"], 1)
            self.assertEqual(hr.ishody[a["opp_id"]]["realized_net_bps"], 450.0)          # 0.3R × 15 % = 4.5 % = 450 bps
            with self.assertRaises(V2.OshibkaV2):
                hr.dobavit_reshenie(a["opp_id"], "BRAIN_V3_POZDNO", "s", 1.0, [], T0 + 51 * H)


if __name__ == "__main__":
    unittest.main()
