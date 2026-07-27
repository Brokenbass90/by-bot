#!/usr/bin/env python3
"""Verify the free Massive Stocks Basic data contract without exposing secrets.

The audit is deliberately small (three requests) to stay below the free
five-requests-per-minute limit.  It verifies the inputs needed for the Alpaca
PIT/data audit: ticker reference, adjusted daily aggregates, and corporate
actions.  It does not claim that two years of history is enough for final
strategy promotion.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT / "configs" / "massive_stocks_local.env"
DEFAULT_OUT = ROOT / "runtime" / "massive_stocks_basic_audit.json"
API_ROOT = "https://api.massive.com"


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _request_json(
    path: str,
    *,
    api_key: str,
    timeout: float,
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "bybit-bot-clean-v28-massive-basic-audit/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {"status": "ERROR", "error": f"HTTP {status}"}
    return status, payload if isinstance(payload, dict) else {}


def _endpoint_result(
    name: str,
    path: str,
    *,
    api_key: str,
    timeout: float,
) -> dict[str, Any]:
    status, payload = _request_json(path, api_key=api_key, timeout=timeout)
    rows = payload.get("results")
    row_count = len(rows) if isinstance(rows, list) else 0
    response_status = str(payload.get("status") or "").upper()
    ok = status == 200 and response_status in {"OK", "SUCCESS"} and row_count > 0
    return {
        "name": name,
        "path": path,
        "http_status": status,
        "response_status": response_status or None,
        "row_count": row_count,
        "ok": ok,
        "error": None if ok else str(payload.get("error") or payload.get("message") or ""),
    }


def build_audit(*, api_key: str, timeout: float = 20.0) -> dict[str, Any]:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=14)
    endpoints = [
        (
            "inactive_ticker_reference",
            "/v3/reference/tickers?"
            + urllib.parse.urlencode(
                {
                    "market": "stocks",
                    "active": "false",
                    "limit": 10,
                    "sort": "ticker",
                }
            ),
        ),
        (
            "adjusted_daily_aggregates",
            f"/v2/aggs/ticker/SPY/range/1/day/{start.isoformat()}/{end.isoformat()}?"
            + urllib.parse.urlencode(
                {"adjusted": "true", "sort": "asc", "limit": 50}
            ),
        ),
        (
            "corporate_actions_splits",
            "/v3/reference/splits?"
            + urllib.parse.urlencode(
                {
                    "limit": 10,
                    "sort": "execution_date",
                    "order": "desc",
                }
            ),
        ),
    ]
    results = [
        _endpoint_result(name, path, api_key=api_key, timeout=timeout)
        for name, path in endpoints
    ]
    all_ok = all(item["ok"] for item in results)
    return {
        "schema": "massive_stocks_basic_audit_v1",
        "plan": "Stocks Basic",
        "request_count": len(results),
        "all_checks_passed": all_ok,
        "checks": results,
        "alpaca_input_status": (
            "connector_and_pit_field_audit_ready"
            if all_ok
            else "blocked_by_massive_api_contract"
        ),
        "promotion_limit": (
            "Two years of Basic history is sufficient for connector and "
            "point-in-time field validation, but not a final long-horizon "
            "strategy robustness claim."
        ),
        "secret_logged": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the free Massive Stocks Basic inputs for Alpaca research"
    )
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--output-json", default=str(DEFAULT_OUT))
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    env_path = Path(args.env_file).expanduser()
    values = _load_env(env_path)
    api_key = (os.environ.get("MASSIVE_API_KEY") or values.get("MASSIVE_API_KEY") or "").strip()
    if not api_key:
        print(f"MASSIVE_API_KEY is missing in {env_path}", file=sys.stderr)
        return 2

    audit = build_audit(api_key=api_key, timeout=max(1.0, args.timeout))
    output_path = Path(args.output_json).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
