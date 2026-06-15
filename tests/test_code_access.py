"""Safety tests for read-only AI code access — must never leak secrets/escape."""

import pytest
from bot.code_access import read_source, list_sources, grep_sources, CodeAccessError


def test_can_read_allowed_strategy_source():
    txt = read_source("bot/strategy_catalog.py")
    assert "strategy" in txt.lower()


def test_refuses_dotenv():
    with pytest.raises(CodeAccessError):
        read_source(".env")


def test_refuses_path_escape():
    for bad in ("../secrets.txt", "/etc/passwd", "~/.ssh/id_rsa", "bot/../.env"):
        with pytest.raises(CodeAccessError):
            read_source(bad)


def test_refuses_dir_outside_allowlist():
    with pytest.raises(CodeAccessError):
        read_source("runtime/live_positions.json")   # runtime not in allowlist


def test_redacts_secret_assignments():
    # test the pure redactor directly (no filesystem dependency)
    from bot.code_access import _redact
    out = _redact("API_KEY = 'leak-me'\nclose = 100.0\nTG_TOKEN: 'abc'\n")
    assert "leak-me" not in out
    assert "abc" not in out
    assert "REDACTED" in out
    assert "close = 100.0" in out          # non-secret code preserved


def test_list_and_grep_work():
    files = list_sources("strategies")
    assert any(f.endswith(".py") for f in files)
    hits = grep_sources("def maybe_signal", "strategies", max_hits=5)
    assert all(":" in h for h in hits)
