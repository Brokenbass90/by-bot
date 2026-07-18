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


def test_refuses_configs_even_when_file_is_inside_repo():
    with pytest.raises(CodeAccessError):
        read_source("configs/web_config.json")
    with pytest.raises(CodeAccessError):
        list_sources("configs")


def test_redacts_secret_assignments():
    # test the pure redactor directly (no filesystem dependency)
    from bot.code_access import _redact
    out = _redact(
        "API_KEY = 'leak-me'\n"
        "close = 100.0\n"
        "TG_TOKEN: 'abc'\n"
        '  \"totp_secret\": \"json-leak\"\n'
    )
    assert "leak-me" not in out
    assert "abc" not in out
    assert "json-leak" not in out
    assert "REDACTED" in out
    assert "close = 100.0" in out          # non-secret code preserved


def test_list_and_grep_work():
    files = list_sources("strategies")
    assert any(f.endswith(".py") for f in files)
    hits = grep_sources("def maybe_signal", "strategies", max_hits=5)
    assert all(":" in h for h in hits)


def test_web_code_search_refuses_configs_and_redacts_json_secrets():
    from web.routes.extra_routes import _redact_source_line, _safe_path

    assert _safe_path("configs/web_config.json") is None
    assert _redact_source_line('  "totp_secret": "must-not-leak"') == "***REDACTED***"


def test_all_web_code_endpoints_require_admin():
    import inspect

    from web.deps import require_admin
    from web.routes import data_routes, extra_routes

    endpoints = (
        data_routes.ai_code_list,
        data_routes.ai_code_read,
        data_routes.ai_code_search,
        extra_routes.ai_code_search,
    )
    for endpoint in endpoints:
        dependency = inspect.signature(endpoint).parameters["_"].default.dependency
        assert dependency is require_admin
