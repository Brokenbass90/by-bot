from __future__ import annotations

import unittest
import hashlib
import json
import tempfile
from pathlib import Path

from research_lab.summarize_att1_btc_eth_presealed import (
    _canonical_sha256,
    build_cohort_diagnostics,
    run,
)


def _row(signal_id: str, symbol: str, ts: int, net_r: str) -> dict[str, object]:
    return {
        "schema_id": "research_live_adapter_parity_v2",
        "sleeve_id": "ATT1",
        "release_or_promotion_authority": False,
        "exception": None,
        "bar_ts": ts,
        "fill_ts_ms": ts,
        "exit_ts_ms": ts + 1,
        "time_stop": {"deadline_ms": ts + 1},
        "symbol": symbol,
        "signal_id": signal_id,
        "side": "short",
        "net_r": net_r,
    }


class CohortDiagnosticTests(unittest.TestCase):
    def test_separates_btc_eth_and_leave_both_out(self) -> None:
        rows = [
            _row("btc-win", "BTCUSDT", 1_700_000_000_000, "1"),
            _row("btc-loss", "BTCUSDT", 1_700_000_001_000, "-0.5"),
            _row("eth-loss", "ETHUSDT", 1_700_000_000_000, "-1"),
            _row("eth-win", "ETHUSDT", 1_700_000_001_000, "0.25"),
            _row("sol-win", "SOLUSDT", 1_700_000_000_000, "2"),
            _row("ada-loss", "ADAUSDT", 1_700_000_000_000, "-0.5"),
        ]

        result = build_cohort_diagnostics(
            rows,
            universe=("BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"),
        )

        self.assertEqual(result["btc_only"]["metrics"]["n"], 2)
        self.assertEqual(result["btc_only"]["metrics"]["sum_r"], "0.5")
        self.assertEqual(result["btc_only"]["metrics"]["profit_factor"], "2")
        self.assertEqual(result["eth_only"]["metrics"]["n"], 2)
        self.assertEqual(result["eth_only"]["metrics"]["sum_r"], "-0.75")
        self.assertEqual(result["eth_only"]["metrics"]["profit_factor"], "0.25")
        self.assertEqual(result["major8_ex_btc_eth"]["symbols"], ["SOLUSDT", "ADAUSDT"])
        self.assertEqual(result["major8_ex_btc_eth"]["metrics"]["n"], 2)
        self.assertEqual(result["major8_ex_btc_eth"]["metrics"]["sum_r"], "1.5")
        self.assertEqual(result["major8_ex_btc_eth"]["metrics"]["profit_factor"], "4")
        self.assertEqual(result["major8_all"]["metrics"]["n"], 6)
        self.assertEqual(result["btc_eth"]["metrics"]["n"], 4)
        self.assertEqual(result["btc_eth"]["metrics"]["side_trade_fraction"], {"short": "1"})
        self.assertEqual(result["btc_eth"]["metrics"]["max_side_trade_fraction"], "1")

    def test_run_verifies_frozen_ledger_hashes_and_writes_non_money_receipt(self) -> None:
        universe = (
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT",
            "LINKUSDT", "LTCUSDT", "DOTUSDT", "SUIUSDT",
        )
        rows = [
            _row(f"signal-{index}", symbol, 1_700_000_000_000 + index * 1_000, "1")
            for index, symbol in enumerate(universe)
        ]
        encoded = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
        ledger_sha = hashlib.sha256(encoded).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "input"
            source.mkdir()
            for mode in ("base", "stress"):
                (source / f"att1_{mode}_live.jsonl").write_bytes(encoded)
            receipt = {
                "schema_id": "att1_sbr1_actual_adapter_parity_receipt_v1",
                "decision": "COMPONENT_PARITY_PASS",
                "live_caller_parity": "BLOCKED",
                "money_authority": False,
                "sealed_holdout_rows_decoded": 0,
                "manifest_path": "configs/research/att1_sbr1_live_native_parity_v1.json",
                "manifest_sha256": "a" * 64,
                "data_bundle_sha256": "b" * 64,
                "source_bundle_sha256": "c" * 64,
                "window": {
                    "start_utc": "2024-03-01T00:00:00Z",
                    "end_utc_exclusive": "2025-10-01T00:00:00Z",
                },
                "sealed_holdout_guard": {
                    "start_utc": "2025-10-01T00:00:00Z",
                    "end_utc_exclusive": "2026-07-01T00:00:00Z",
                    "must_not_read": True,
                },
                "sleeves": {
                    "ATT1": {
                        "reports": {
                            "base": {"live_ledger_sha256": ledger_sha},
                            "stress": {"live_ledger_sha256": ledger_sha},
                        }
                    }
                },
            }
            receipt["receipt_sha256"] = _canonical_sha256(receipt)
            receipt_path = source / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            receipt_file_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
            contract = {
                "schema_id": "att1_btc_eth_presealed_diagnostic_contract_v1",
                "authority": "research_only_exact_frozen_input_no_live_no_broker_no_money_no_promotion",
                "universe": list(universe),
                "expected_source": {
                    "receipt_file_sha256": receipt_file_sha,
                    "receipt_sha256": receipt["receipt_sha256"],
                    "manifest_path": receipt["manifest_path"],
                    "manifest_sha256": receipt["manifest_sha256"],
                    "data_bundle_sha256": receipt["data_bundle_sha256"],
                    "source_bundle_sha256": receipt["source_bundle_sha256"],
                    "att1_base_live_sha256": ledger_sha,
                    "att1_stress_live_sha256": ledger_sha,
                },
                "sealed_holdout_guard": receipt["sealed_holdout_guard"],
            }
            contract["config_fingerprint_sha256"] = _canonical_sha256(contract)
            contract_path = Path(temporary) / "contract.json"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            output = Path(temporary) / "receipt.json"

            result = run(source, output, universe=universe, contract_path=contract_path)

            self.assertEqual(result["schema_id"], "att1_btc_eth_presealed_diagnostic_v1")
            self.assertFalse(result["money_authority"])
            self.assertFalse(result["release_or_promotion_authority"])
            self.assertEqual(result["sealed_holdout_rows_decoded"], 0)
            self.assertEqual(result["modes"]["base"]["cohorts"]["btc_only"]["metrics"]["n"], 1)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), result)


if __name__ == "__main__":
    unittest.main()
