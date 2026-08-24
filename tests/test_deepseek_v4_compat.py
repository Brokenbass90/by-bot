from __future__ import annotations

import pytest

from bot.deepseek_overlay import (
    CURRENT_DEEPSEEK_MODEL,
    DeepSeekHTTPError,
    DeepSeekOverlay,
    _normalize_model,
    _response_error_text,
)


@pytest.fixture(autouse=True)
def _isolated_attempt_ledger(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "DEEPSEEK_ATTEMPT_LEDGER_PATH", str(tmp_path / "attempts.sqlite3")
    )
    monkeypatch.setenv("DEEPSEEK_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, *, reason="", headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.reason = reason
        self.headers = headers or {}

    def json(self):
        return self._payload


def test_retired_model_names_fail_forward_to_v4_flash() -> None:
    assert _normalize_model("") == CURRENT_DEEPSEEK_MODEL
    assert _normalize_model("deepseek-chat") == CURRENT_DEEPSEEK_MODEL
    assert _normalize_model("deepseek-reasoner") == CURRENT_DEEPSEEK_MODEL
    assert _normalize_model("deepseek-v4-pro") == "deepseek-v4-pro"


def test_v4_operator_payload_disables_thinking(monkeypatch) -> None:
    overlay = DeepSeekOverlay()
    overlay.cfg.api_key = "test-key"
    overlay.cfg.model = CURRENT_DEEPSEEK_MODEL
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return _FakeResponse(
            payload={
                "choices": [
                    {"message": {"content": "готово"}, "finish_reason": "stop"}
                ]
            }
        )

    monkeypatch.setattr("bot.deepseek_overlay.requests.post", fake_post)
    content, finish_reason = overlay._request_chat_completion(
        [{"role": "user", "content": "status"}]
    )

    assert content == "готово"
    assert finish_reason == "stop"
    assert captured["json"]["model"] == CURRENT_DEEPSEEK_MODEL
    assert captured["json"]["thinking"] == {"type": "disabled"}
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_http_error_is_useful_but_does_not_echo_response_body(monkeypatch) -> None:
    overlay = DeepSeekOverlay()
    overlay.cfg.api_key = "secret-key"
    overlay.cfg.model = CURRENT_DEEPSEEK_MODEL

    def fake_post(*args, **kwargs):
        return _FakeResponse(
            400,
            {
                "error": {
                    "message": "Unsupported model name",
                    "type": "invalid_request_error",
                },
                "debug": "secret-key",
            },
            headers={"x-request-id": "req-123"},
        )

    monkeypatch.setattr("bot.deepseek_overlay.requests.post", fake_post)
    with pytest.raises(DeepSeekHTTPError) as exc_info:
        overlay._request_chat_completion([{"role": "user", "content": "status"}])

    text = str(exc_info.value)
    assert "HTTP 400" in text
    assert "Unsupported model name" in text
    assert "request_id=req-123" in text
    assert "secret-key" not in text


def test_response_error_falls_back_to_http_reason() -> None:
    resp = _FakeResponse(503, {}, reason="Service Unavailable")
    assert _response_error_text(resp, model=CURRENT_DEEPSEEK_MODEL) == (
        "HTTP 503 | model=deepseek-v4-flash | Service Unavailable"
    )
