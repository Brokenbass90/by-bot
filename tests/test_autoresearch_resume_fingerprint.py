from scripts.run_strategy_autoresearch import (
    _candidate_metadata,
    _resume_matches,
    _score_candidate,
    _write_candidate_metadata,
)


def test_resume_requires_matching_full_candidate_fingerprint(tmp_path) -> None:
    spec = {
        "name": "package_test",
        "cache_only": True,
        "command": ["python", "runner.py", "--tag", "{tag}"],
        "base_env": {"ARF1_MIN_RSI": "52.0"},
    }
    first = _candidate_metadata(spec, {"PFS1_PUMP_MIN_PCT": "2.5"})
    _write_candidate_metadata(tmp_path, first)

    assert _resume_matches(tmp_path, first) is True

    changed_base = {
        **spec,
        "base_env": {"ARF1_MIN_RSI": "48.0"},
    }
    second = _candidate_metadata(changed_base, {"PFS1_PUMP_MIN_PCT": "2.5"})

    assert _resume_matches(tmp_path, second) is False


def test_legacy_run_without_fingerprint_is_not_reused(tmp_path) -> None:
    metadata = _candidate_metadata({"name": "package_test"}, {})

    assert _resume_matches(tmp_path, metadata) is False


def test_score_candidate_enforces_winrate_and_avg_win_loss_ratio() -> None:
    spec = {
        "constraints": {
            "min_trades": 10,
            "min_profit_factor": 1.1,
            "max_drawdown": 10,
            "min_net_pnl": 1,
            "min_winrate": 0.45,
            "min_avg_win_loss_ratio": 1.2,
        }
    }
    weak_summary = {
        "trades": "50",
        "net_pnl": "5",
        "profit_factor": "1.3",
        "winrate": "0.40",
        "avg_win": "1.0",
        "avg_loss": "-1.0",
        "max_drawdown": "3.0",
    }

    passed, reasons, _score = _score_candidate(weak_summary, spec)

    assert passed is False
    assert "wr<0.45" in reasons
    assert "avg_wl<1.2" in reasons

    strong_summary = {
        **weak_summary,
        "winrate": "0.50",
        "avg_win": "1.5",
        "avg_loss": "-1.0",
    }
    passed, reasons, _score = _score_candidate(strong_summary, spec)

    assert passed is True
    assert reasons == ""
