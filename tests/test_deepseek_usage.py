from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
import requests

from bot.deepseek_overlay import (
    CURRENT_DEEPSEEK_MODEL,
    DeepSeekBudgetError,
    DeepSeekOverlay,
)
from bot.deepseek_usage import (
    append_deepseek_usage,
    count_deepseek_attempts,
    extract_usage,
    finalize_deepseek_attempt,
    normalize_deepseek_model,
    prompt_char_count,
    read_deepseek_attempts,
    reserve_deepseek_attempt,
    seed_attempt_ledger_from_legacy_audit,
)
from web.routes import ai_routes


class _FakeRequestsResponse:
    status_code = 200
    headers = {}
    reason = "OK"

    def json(self):
        return {
            "choices": [
                {"message": {"content": "готово"}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": 101,
                "completion_tokens": 17,
                "total_tokens": 118,
                "prompt_cache_hit_tokens": 80,
                "prompt_cache_miss_tokens": 21,
            },
        }


class _FakeUrlopenResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(_FakeRequestsResponse().json()).encode("utf-8")


def test_usage_row_has_actual_counters_but_no_prompt_or_secret(tmp_path) -> None:
    path = tmp_path / "usage.jsonl"
    assert append_deepseek_usage(
        source="unit_test",
        model="deepseek-chat",
        max_tokens=300,
        prompt_chars=1234,
        latency_ms=42,
        status="ok",
        response_payload={
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "prompt_cache_hit_tokens": 75,
                "prompt_cache_miss_tokens": 25,
            },
            "choices": [{"message": {"content": "TOP SECRET RESPONSE"}}],
        },
        path=path,
    )
    raw = path.read_text(encoding="utf-8")
    row = json.loads(raw)
    assert row["model"] == CURRENT_DEEPSEEK_MODEL
    assert row["prompt_tokens"] == 100
    assert row["prompt_cache_hit_tokens"] == 75
    assert row["prompt_cache_miss_tokens"] == 25
    assert row["prompt_chars"] == 1234
    assert "TOP SECRET" not in raw
    assert "choices" not in row


def test_usage_helpers_are_conservative() -> None:
    assert normalize_deepseek_model("deepseek-reasoner") == CURRENT_DEEPSEEK_MODEL
    assert normalize_deepseek_model("deepseek-v4-pro") == "deepseek-v4-pro"
    assert prompt_char_count(
        [{"role": "user", "content": "abc"}, {"role": "assistant", "content": "de"}]
    ) == len("userabcassistantde")
    assert extract_usage({"usage": {"prompt_tokens": "5", "total_tokens": -1}}) == {
        "prompt_tokens": 5
    }


def test_overlay_records_provider_usage(monkeypatch, tmp_path) -> None:
    usage_path = tmp_path / "overlay_usage.jsonl"
    ledger_path = tmp_path / "overlay_attempts.sqlite3"
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("DEEPSEEK_USAGE_LOG_PATH", str(usage_path))
    monkeypatch.setenv("DEEPSEEK_ATTEMPT_LEDGER_PATH", str(ledger_path))
    monkeypatch.setenv("DEEPSEEK_AUDIT_LOG_PATH", str(audit_path))
    overlay = DeepSeekOverlay()
    overlay.cfg.api_key = "not-a-real-key"
    overlay.cfg.model = CURRENT_DEEPSEEK_MODEL
    overlay.cfg.completion_max_tokens = 300
    observed_reserved = []

    def fake_post(*_args, **_kwargs):
        rows = read_deepseek_attempts(path=ledger_path)
        observed_reserved.append(rows[-1]["status"])
        return _FakeRequestsResponse()

    monkeypatch.setattr("bot.deepseek_overlay.requests.post", fake_post)

    content, finish = overlay._request_chat_completion(
        [{"role": "user", "content": "PRIVATE_QUERY_DO_NOT_STORE"}],
        source="test_overlay",
    )

    assert (content, finish) == ("готово", "stop")
    rows = read_deepseek_attempts(path=ledger_path)
    assert len(rows) == 1
    row = rows[0]
    assert observed_reserved == ["reserved"]
    assert row["source"] == "test_overlay"
    assert row["status"] == "ok"
    assert row["prompt_tokens"] == 101
    assert row["completion_tokens"] == 17
    assert row["prompt_cache_hit_tokens"] == 80
    assert "PRIVATE_QUERY_DO_NOT_STORE" not in json.dumps(row)
    assert "not-a-real-key" not in json.dumps(row)


def test_atomic_attempt_reservation_is_concurrency_safe(tmp_path) -> None:
    ledger_path = tmp_path / "concurrent.sqlite3"
    now_ts = int(datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc).timestamp())

    def reserve(_index):
        return reserve_deepseek_attempt(
            source="concurrency_test",
            model=CURRENT_DEEPSEEK_MODEL,
            max_tokens=400,
            prompt_chars=123,
            daily_cap=5,
            path=ledger_path,
            now_ts=now_ts,
        )

    with ThreadPoolExecutor(max_workers=16) as pool:
        reservations = list(pool.map(reserve, range(40)))

    accepted = [item for item in reservations if item is not None]
    assert len(accepted) == 5
    assert len({item.attempt_id for item in accepted}) == 5
    assert count_deepseek_attempts(path=ledger_path, now_ts=now_ts) == 5


def test_finalize_updates_one_sanitized_row(tmp_path) -> None:
    ledger_path = tmp_path / "one_row.sqlite3"
    reservation = reserve_deepseek_attempt(
        source="unit",
        model=CURRENT_DEEPSEEK_MODEL,
        max_tokens=400,
        prompt_chars=999,
        daily_cap=1,
        path=ledger_path,
    )
    assert reservation is not None
    assert finalize_deepseek_attempt(
        reservation,
        latency_ms=7,
        status="ok",
        response_payload={
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            "choices": [{"message": {"content": "BUY_NOW SECRET"}}],
        },
    )

    rows = read_deepseek_attempts(path=ledger_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["total_tokens"] == 12
    encoded = json.dumps(rows[0])
    assert "BUY_NOW" not in encoded
    assert "SECRET" not in encoded


def test_legacy_audit_seed_is_idempotent_and_counts_toward_cap(tmp_path) -> None:
    now_ts = int(datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc).timestamp())
    audit_path = tmp_path / "legacy.jsonl"
    ledger_path = tmp_path / "migration.sqlite3"
    audit_path.write_text(
        "\n".join(
            [
                json.dumps({"ts": now_ts - 10, "status": "ok", "question": "secret"}),
                json.dumps({"ts": now_ts - 5, "kind": "truth_gate_blocked"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert seed_attempt_ledger_from_legacy_audit(
        audit_path, path=ledger_path, now_ts=now_ts
    ) == 1
    assert seed_attempt_ledger_from_legacy_audit(
        audit_path, path=ledger_path, now_ts=now_ts
    ) == 1
    assert count_deepseek_attempts(path=ledger_path, now_ts=now_ts) == 1
    rows = read_deepseek_attempts(path=ledger_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "legacy_audit_seed"
    assert "secret" not in json.dumps(rows[0])
    assert (
        reserve_deepseek_attempt(
            source="after_deploy",
            model=CURRENT_DEEPSEEK_MODEL,
            max_tokens=400,
            prompt_chars=10,
            daily_cap=1,
            path=ledger_path,
            now_ts=now_ts,
        )
        is None
    )


def test_timeout_retries_each_reserve_and_cannot_bypass_cap(monkeypatch, tmp_path) -> None:
    ledger_path = tmp_path / "retry.sqlite3"
    monkeypatch.setenv("DEEPSEEK_ATTEMPT_LEDGER_PATH", str(ledger_path))
    monkeypatch.setenv("DEEPSEEK_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    overlay = DeepSeekOverlay()
    overlay.cfg.api_key = "test-only"
    overlay.cfg.daily_request_cap = 2
    overlay.cfg.timeout_retries = 3
    overlay.cfg.retry_backoff_sec = 0
    calls = {"n": 0}

    def timeout(*_args, **_kwargs):
        calls["n"] += 1
        raise requests.exceptions.Timeout("test")

    monkeypatch.setattr("bot.deepseek_overlay.requests.post", timeout)

    with pytest.raises(DeepSeekBudgetError):
        overlay._request_chat_completion([{"role": "user", "content": "private"}])

    assert calls["n"] == 2
    rows = read_deepseek_attempts(path=ledger_path)
    assert len(rows) == 2
    assert all(row["status"] == "error" for row in rows)


def test_second_completion_call_cannot_bypass_single_attempt_cap(monkeypatch, tmp_path) -> None:
    ledger_path = tmp_path / "continuation.sqlite3"
    monkeypatch.setenv("DEEPSEEK_ATTEMPT_LEDGER_PATH", str(ledger_path))
    monkeypatch.setenv("DEEPSEEK_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    overlay = DeepSeekOverlay()
    overlay.cfg.api_key = "test-only"
    overlay.cfg.daily_request_cap = 1
    calls = {"n": 0}

    def success(*_args, **_kwargs):
        calls["n"] += 1
        return _FakeRequestsResponse()

    monkeypatch.setattr("bot.deepseek_overlay.requests.post", success)

    assert overlay._request_chat_completion([{"role": "user", "content": "part1"}]) == (
        "готово",
        "stop",
    )
    with pytest.raises(DeepSeekBudgetError):
        overlay._request_chat_completion([{"role": "user", "content": "part2"}])

    assert calls["n"] == 1
    assert count_deepseek_attempts(path=ledger_path) == 1


def test_web_client_normalizes_model_and_records_usage(monkeypatch, tmp_path) -> None:
    usage_path = tmp_path / "web_usage.jsonl"
    captured = {}
    monkeypatch.setenv("DEEPSEEK_USAGE_LOG_PATH", str(usage_path))

    def fake_urlopen(req, **kwargs):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _FakeUrlopenResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    reply, model = ai_routes._deepseek_chat_completion(
        api_key="not-a-real-key",
        model="deepseek-chat",
        messages=[{"role": "user", "content": "status"}],
        max_tokens=250,
        temperature=0.2,
        timeout_sec=3,
        source="test_web",
    )

    assert reply == "готово"
    assert model == CURRENT_DEEPSEEK_MODEL
    assert captured["payload"]["model"] == CURRENT_DEEPSEEK_MODEL
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    row = json.loads(usage_path.read_text(encoding="utf-8"))
    assert row["source"] == "test_web"
    assert row["total_tokens"] == 118


def test_web_context_bound_keeps_authority_lines() -> None:
    text = (
        "=== BOT CONTEXT [now] ===\n"
        "BOT MIRROR: FRESH\n"
        + ("evidence row\n" * 500)
        + "WEB LIVE TRUTH GATE: control_recommendations_allowed=False\n"
        + "=== AVAILABLE CONTROL COMMANDS ===\n"
        + "Trading mutations are intentionally blocked\n"
    )
    bounded = ai_routes._bounded_web_context(text, max_chars=2_000)
    assert len(bounded) <= 2_000
    assert "CONTEXT COST BOUNDARY" in bounded
    assert "BOT MIRROR: FRESH" in bounded
    assert "WEB LIVE TRUTH GATE" in bounded
    assert "Trading mutations are intentionally blocked" in bounded


def test_web_history_bounds_and_strips_internal_timestamps(monkeypatch) -> None:
    monkeypatch.setattr(ai_routes, "_HISTORY_MAX", 4)
    monkeypatch.setattr(ai_routes, "_WEB_MESSAGE_MAX_CHARS", 10)
    monkeypatch.setattr(ai_routes, "_WEB_HISTORY_MAX_CHARS", 14)
    result = ai_routes._bounded_chat_messages(
        [
            {"role": "user", "content": "old", "ts": 1},
            {"role": "assistant", "content": "0123456789ABCDE", "ts": 2},
            {"role": "user", "content": "UVWXYZ", "ts": 3},
        ]
    )
    assert sum(len(item["content"]) for item in result) <= 14
    assert all(set(item) == {"role", "content"} for item in result)
    assert result[-1]["content"] == "UVWXYZ"


def test_setup_cache_is_ttl_bounded(monkeypatch) -> None:
    monkeypatch.setattr(ai_routes, "_SETUP_CACHE_TTL_SEC", 10)
    ai_routes._SETUP_AI_CACHE.clear()
    body = ai_routes.SetupAnalysisRequest(
        symbol="BTCUSDT",
        side="short",
        setup_type="resistance",
        strategy="flat",
    )
    key = ai_routes._setup_cache_key(
        body,
        regime="flat",
        provider="deepseek",
        model=CURRENT_DEEPSEEK_MODEL,
    )
    response = ai_routes.SetupAnalysisResponse(
        verdict="ok",
        reasoning="Проверяемый ответ.",
        risk_note="Это не разрешение на сделку.",
        model=CURRENT_DEEPSEEK_MODEL,
    )
    ai_routes._setup_cache_set(key, response, now=100.0)
    assert ai_routes._setup_cache_get(key, now=109.0) is not None
    assert ai_routes._setup_cache_get(key, now=111.0) is None
