from __future__ import annotations

import io
import json

from scripts import verify_massive_stocks_basic as mod


class _Response:
    status = 200

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_basic_audit_uses_three_bearer_requests_and_never_returns_key(monkeypatch) -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return _Response({"status": "OK", "results": [{"ticker": "SPY"}]})

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)

    audit = mod.build_audit(api_key="super-secret", timeout=4.0)

    assert audit["all_checks_passed"] is True
    assert audit["request_count"] == 3
    assert audit["secret_logged"] is False
    assert "super-secret" not in json.dumps(audit)
    assert len(requests) == 3
    assert all(
        request.headers["Authorization"] == "Bearer super-secret"
        for request, _ in requests
    )


def test_env_loader_ignores_comments_and_reads_key(tmp_path) -> None:
    path = tmp_path / "massive.env"
    path.write_text(
        "# local only\nMASSIVE_API_KEY='abc123'\nIGNORED_LINE\n",
        encoding="utf-8",
    )

    assert mod._load_env(path) == {"MASSIVE_API_KEY": "abc123"}
