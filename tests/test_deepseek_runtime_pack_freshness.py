import json
import os
import time
from pathlib import Path

import smart_pump_reversal_bot as live


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_telegram_ai_excludes_stale_auxiliary_runtime_packs(monkeypatch, tmp_path) -> None:
    extras = tmp_path / "runtime" / "ai_context" / "extras.json"
    ohlc = tmp_path / "runtime" / "ai_context" / "ohlc_and_logs.json"
    blocker = tmp_path / "runtime" / "crypto_blocker" / "latest.json"
    _write(extras, {"generated_at_utc": "fresh", "trade_history": {}})
    _write(ohlc, {"generated_at_utc": "fresh", "ohlc": {}})
    _write(blocker, {"generated_at_utc": "fresh", "sleeves": {}})
    monkeypatch.setattr(live, "ROOT_DIR", tmp_path)

    assert live._compact_ai_extras_for_deepseek()
    assert live._compact_ai_ohlc_logs_for_deepseek()
    assert live._compact_crypto_blocker_for_deepseek()

    old = time.time() - live.AI_AUX_PACK_MAX_AGE_SEC - 10
    for path in (extras, ohlc, blocker):
        os.utime(path, (old, old))

    assert live._compact_ai_extras_for_deepseek() == {}
    assert live._compact_ai_ohlc_logs_for_deepseek() == {}
    assert live._compact_crypto_blocker_for_deepseek() == {}


def test_runtime_authority_classifies_every_live_loop_flag() -> None:
    snapshot = live._strategy_runtime_authority_snapshot()

    assert snapshot["complete"] is True
    assert snapshot["unclassified_sleeves"] == []
    assert set(snapshot["components"]) == {name for name, _enabled in live._strategy_flag_pairs()}
