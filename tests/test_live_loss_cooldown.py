from __future__ import annotations

import ast
import json
from pathlib import Path

from bot.live_loss_cooldown import record_loss_cooldown, restore_loss_cooldowns


ROOT = Path(__file__).resolve().parents[1]


def test_record_loss_cooldown_only_blocks_losses():
    state = {}
    assert record_loss_cooldown(
        state, symbol="apeusdt", pnl=-0.1, closed_ts=1_000, cooldown_sec=300
    ) == 1_300
    assert state == {"APEUSDT": 1_300}
    assert record_loss_cooldown(
        state, symbol="APEUSDT", pnl=0.2, closed_ts=1_100, cooldown_sec=300
    ) == 1_300


def test_restore_loss_cooldown_survives_restart(tmp_path):
    path = tmp_path / "live_trade_events.jsonl"
    rows = [
        {"event": "close", "strategy": "range", "symbol": "OLDUSDT", "pnl": -1, "ts": 100},
        {"event": "close", "strategy": "range", "symbol": "APEUSDT", "pnl": -0.1, "ts": 900},
        {"event": "close", "strategy": "range", "symbol": "WINUSDT", "pnl": 0.2, "ts": 950},
        {"event": "close", "strategy": "other", "symbol": "OTHERUSDT", "pnl": -1, "ts": 990},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    assert restore_loss_cooldowns(
        path, strategy="range", cooldown_sec=300, now_ts=1_000
    ) == {"APEUSDT": 1_200}


def test_range_loss_cooldown_is_wired_into_entry_close_and_startup():
    tree = ast.parse((ROOT / "smart_pump_reversal_bot.py").read_text(encoding="utf-8"))
    names_by_function = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names_by_function[node.name] = {
                child.id for child in ast.walk(node) if isinstance(child, ast.Name)
            }

    assert "_RANGE_LOSS_COOLDOWN_UNTIL" in names_by_function["try_range_entry_async"]
    assert "record_loss_cooldown" in names_by_function["_finalize_and_report_closed"]
    assert "restore_loss_cooldowns" in names_by_function["main"]
