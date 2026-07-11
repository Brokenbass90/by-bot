import json

from scripts import weekly_trade_forensics_ai_report as report


def test_notice_defines_missing_candles_as_forensic_cache_gap(monkeypatch, tmp_path):
    monkeypatch.setattr(report, "ROOT", tmp_path)
    notice = report._data_quality_notice()

    assert "post-hoc forensic cache" in notice
    assert "не доказательство сбоя live-свечей/выходов" in notice
    assert "смешанный исторический accounting cohort" in notice
    assert "при N<20 verdict запрещён" in notice


def test_runtime_truth_separates_live_money_from_shadow(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "bot_heartbeat.json").write_text(
        json.dumps(
            {
                "regime": "bull_chop",
                "trade_on": True,
                "dry_run": False,
                "strategy_runtime_config": {
                    "enabled": {"att1": True, "range": True, "off": False},
                    "risk_mult": {"att1": 0.1, "range": 0.0, "off": 1.0},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(report, "ROOT", tmp_path)
    monkeypatch.setenv("ATT1_EDGE_START_TS", "1783000000")

    truth = report._runtime_truth()

    assert truth["live_money_sleeves"] == ["att1"]
    assert truth["shadow_sleeves"] == ["range"]
    assert truth["risk_mult"]["att1"] == 0.1
    assert truth["att1_edge_start_ts"] == "1783000000"


def test_ai_prompt_contains_contract_and_runtime_truth(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "bot_heartbeat.json").write_text(
        json.dumps(
            {
                "strategy_runtime_config": {
                    "enabled": {"att1": True},
                    "risk_mult": {"att1": 0.1},
                }
            }
        ),
        encoding="utf-8",
    )

    captured = {}

    class FakeOverlay:
        def is_ready(self):
            return True

        def ask(self, prompt, snapshot):
            captured["prompt"] = prompt
            captured["snapshot"] = snapshot
            return "ok"

    monkeypatch.setattr(report, "ROOT", tmp_path)
    monkeypatch.setenv("FORENSICS_AI_ENABLE", "1")
    monkeypatch.setitem(__import__("sys").modules, "bot.deepseek_overlay", type("M", (), {"DeepSeekOverlay": FakeOverlay}))

    assert report._ai_interpret("backtest", "live") == "ok"
    assert "missing_candles означает только отсутствие свечей" in captured["prompt"]
    assert "historical accounting cohort" in captured["prompt"]
    assert captured["snapshot"]["runtime_truth"]["live_money_sleeves"] == ["att1"]
