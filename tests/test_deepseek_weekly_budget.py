import sys
import types

from scripts import deepseek_weekly_cron as weekly


def test_tune_phase_obeys_hard_request_cap(monkeypatch) -> None:
    calls: list[str] = []
    agent = types.ModuleType("deepseek_autoresearch_agent")
    agent.build_research_context = lambda: {"research": "test"}

    def fake_tune(strategy, _overlay, _snapshot):
        calls.append(strategy)
        return "proposal"

    agent.tune_strategy = fake_tune
    overlay_module = types.ModuleType("deepseek_overlay")

    class FakeOverlay:
        def is_ready(self):
            return True

    overlay_module.DeepSeekOverlay = FakeOverlay
    monkeypatch.setitem(sys.modules, "deepseek_autoresearch_agent", agent)
    monkeypatch.setitem(sys.modules, "deepseek_overlay", overlay_module)
    monkeypatch.setattr(weekly, "build_operator_snapshot", None)
    monkeypatch.setattr(weekly.time, "sleep", lambda _seconds: None)

    result = weekly._run_tune_phase(
        ["breakout", "flat", "asc1"],
        dry_run=False,
        quiet=True,
        request_cap=1,
    )

    assert calls == ["breakout"]
    assert any("skipped_by_weekly_api_cap=2" in row for row in result)


def test_tune_dry_run_reports_zero_explicit_cap() -> None:
    result = weekly._run_tune_phase(
        ["breakout", "flat"],
        dry_run=True,
        quiet=True,
        request_cap=0,
    )

    assert result[0] == "[dry-run] Would tune: none"
    assert "skipped_by_weekly_api_cap=2" in result[1]


def test_weekly_report_exposes_budget_skips() -> None:
    text = weekly._format_universe_section(
        {"ASC1": {"skipped": "weekly_api_cap"}}
    )

    assert "ASC1: skipped (weekly_api_cap)" in text
