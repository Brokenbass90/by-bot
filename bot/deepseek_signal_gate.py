"""DeepSeek Signal Gate — shadow-mode AI overlay поверх существующих стратегий.

Идея: стратегия уже сгенерировала сигнал; DeepSeek получает контекст и говорит
yes/no/reduce. В **shadow-mode** вердикт ИГНОРИРУЕТСЯ для торговли — только
пишется в JSONL для post-hoc анализа («если бы слушали AI, было бы X»).

Стадии запуска (по AI_OVERLAY_GATE_CONCEPT_20260429.md):
  - shadow (default)  — log only, не блокирует сделки.
  - block_only        — может блокировать (skip), но не reduce.
  - full              — может block / reduce (×0.5) / approve.
  - proactive         — отдельный скрипт, может предлагать risk_mult changes.

Env vars:
  DEEPSEEK_GATE_ENABLED          (0)        — мастер-flag. 0 = ничего не делает.
  DEEPSEEK_GATE_MODE             (shadow)   — shadow|block_only|full
  DEEPSEEK_API_KEY               required для real call (если нет — пишет в лог 'no_key')
  DEEPSEEK_API_URL               (https://api.deepseek.com/v1/chat/completions)
  DEEPSEEK_MODEL                 (deepseek-chat)
  DEEPSEEK_GATE_TIMEOUT_SEC      (4.0)      — fallback на approve если таймаут
  DEEPSEEK_GATE_LOG_PATH         (runtime/ai_gate_log.jsonl)
  DEEPSEEK_GATE_RATE_LIMIT_RPM   (30)       — max requests per minute

Usage (intended hook in smart_pump_reversal_bot.py перед order placement):
    from bot.deepseek_signal_gate import gate_signal
    verdict = gate_signal(strategy="alt_trendline_touch_v1", symbol="BTCUSDT",
                          side="long", regime="bull_chop",
                          price=65000, sl=64200, tp=66500,
                          recent_trades=[...], context={...})
    if verdict.action == "block":
        return  # skip
    elif verdict.action == "reduce":
        risk_mult *= verdict.risk_factor  # e.g. 0.5
    # else 'approve' — продолжаем как обычно

Cost: ~$0.003/call * 30 calls/day = $0.09/day = $3/month.
"""
from __future__ import annotations

import json
import os
import time
from collections import deque
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional
from urllib import error, request


_RATE_LIMIT_WINDOW = deque()  # type: deque[float]


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip()


def _env_float(name: str, default: float) -> float:
    try: return float(os.getenv(name, "") or default)
    except: return default


def _env_int(name: str, default: int) -> int:
    try: return int(os.getenv(name, "") or default)
    except: return default


@dataclass
class GateVerdict:
    action: str          # "approve" | "block" | "reduce" | "skip_no_call"
    risk_factor: float   # 1.0=approve, 0.5=reduce, 0.0=block
    confidence: float    # 0.0..1.0
    reason: str
    latency_ms: float
    cost_estimate_usd: float


def _check_rate_limit(rpm_limit: int) -> bool:
    now = time.time()
    while _RATE_LIMIT_WINDOW and now - _RATE_LIMIT_WINDOW[0] > 60:
        _RATE_LIMIT_WINDOW.popleft()
    if len(_RATE_LIMIT_WINDOW) >= rpm_limit:
        return False
    _RATE_LIMIT_WINDOW.append(now)
    return True


def _log_gate_event(event: dict, log_path: Path) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        event.setdefault("ts", int(time.time()))
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _build_prompt(
    strategy: str, symbol: str, side: str, regime: str,
    price: float, sl: float, tp: Optional[float],
    recent_trades: list, context: dict,
) -> tuple[str, str]:
    """Возвращает (system_msg, user_msg) для DeepSeek API."""
    system = (
        "You are a risk gate for a crypto trading bot. You receive a candidate trade "
        "from a working strategy. Your job is to APPROVE, BLOCK, or REDUCE the size. "
        "Be conservative when conditions look risky (overextended trend, news, low liquidity). "
        "Default to APPROVE — only block/reduce if you see specific danger. "
        "Respond with JSON ONLY: "
        '{"action": "approve|block|reduce", "confidence": 0.0..1.0, "reason": "..."}'
    )

    risk_pct = abs(price - sl) / price * 100 if price > 0 else 0
    rr = abs(tp - price) / abs(price - sl) if (tp and tp != price and sl != price) else 0

    recent_summary = []
    for t in (recent_trades or [])[-5:]:
        recent_summary.append(f"{t.get('strategy','?')} {t.get('side','?')} pnl={t.get('pnl',0):+.2f}")

    user = (
        f"Strategy: {strategy} | Symbol: {symbol} | Side: {side} | Regime: {regime}\n"
        f"Entry: {price:.4f} | SL: {sl:.4f} | TP: {tp if tp else 'none'} | "
        f"SL distance: {risk_pct:.2f}% | RR: {rr:.1f}\n"
        f"Recent 5 trades: {' | '.join(recent_summary) if recent_summary else 'none'}\n"
        f"Context: {json.dumps(context, ensure_ascii=False)[:300]}"
    )
    return system, user


def _call_deepseek(system: str, user: str, api_key: str, api_url: str, model: str, timeout: float) -> dict:
    """Возвращает {action, confidence, reason} или {error, ...}."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0,
        "max_tokens": 100,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(body).encode()
    req = request.Request(
        url=api_url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
        content = payload["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return {
            "action": str(parsed.get("action", "approve")).lower(),
            "confidence": float(parsed.get("confidence", 0.5)),
            "reason": str(parsed.get("reason", ""))[:200],
            "tokens": payload.get("usage", {}),
        }
    except (error.URLError, error.HTTPError, KeyError, ValueError, TimeoutError) as e:
        return {"error": str(e)[:120]}


def gate_signal(
    strategy: str, symbol: str, side: str, regime: str,
    price: float, sl: float, tp: Optional[float] = None,
    recent_trades: Optional[list] = None,
    context: Optional[dict] = None,
) -> GateVerdict:
    """Главная функция — вызывается перед order placement.

    Returns GateVerdict. В shadow-mode caller игнорирует action; в block/full —
    смотрит action и risk_factor.
    """
    enabled = _env_bool("DEEPSEEK_GATE_ENABLED", False)
    mode = _env_str("DEEPSEEK_GATE_MODE", "shadow").lower()
    if mode not in {"shadow", "block_only", "full"}:
        mode = "shadow"
    log_path = Path(_env_str("DEEPSEEK_GATE_LOG_PATH", "runtime/ai_gate_log.jsonl"))

    t0 = time.time()
    if not enabled:
        v = GateVerdict("approve", 1.0, 1.0, "gate_disabled", 0.0, 0.0)
        _log_gate_event({"event": "disabled", "verdict": asdict(v),
                         "strategy": strategy, "symbol": symbol, "side": side}, log_path)
        return v

    rpm = _env_int("DEEPSEEK_GATE_RATE_LIMIT_RPM", 30)
    if not _check_rate_limit(rpm):
        v = GateVerdict("approve", 1.0, 0.5, "rate_limit_fallback", 0.0, 0.0)
        _log_gate_event({"event": "rate_limit", "verdict": asdict(v),
                         "strategy": strategy, "symbol": symbol}, log_path)
        return v

    api_key = _env_str("DEEPSEEK_API_KEY", "")
    if not api_key:
        v = GateVerdict("approve", 1.0, 0.5, "no_api_key", 0.0, 0.0)
        _log_gate_event({"event": "no_key", "verdict": asdict(v)}, log_path)
        return v

    api_url = _env_str("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
    model = _env_str("DEEPSEEK_MODEL", "deepseek-chat")
    timeout = _env_float("DEEPSEEK_GATE_TIMEOUT_SEC", 4.0)

    system, user = _build_prompt(
        strategy=strategy, symbol=symbol, side=side, regime=regime,
        price=price, sl=sl, tp=tp,
        recent_trades=recent_trades or [],
        context=context or {},
    )

    api_resp = _call_deepseek(system, user, api_key, api_url, model, timeout)
    latency_ms = (time.time() - t0) * 1000.0

    if "error" in api_resp:
        v = GateVerdict("approve", 1.0, 0.5, f"api_error:{api_resp['error']}", latency_ms, 0.0)
        _log_gate_event({
            "event": "api_error", "error": api_resp["error"],
            "verdict": asdict(v), "strategy": strategy, "symbol": symbol,
        }, log_path)
        return v

    action = api_resp.get("action", "approve")
    if action not in {"approve", "block", "reduce"}:
        action = "approve"

    risk_factor = {"approve": 1.0, "reduce": 0.5, "block": 0.0}[action]

    # In shadow mode — overwrite to approve regardless, but still log AI decision
    effective_action = action
    effective_risk = risk_factor
    if mode == "shadow":
        effective_action = "approve"
        effective_risk = 1.0
    elif mode == "block_only" and action == "reduce":
        effective_action = "approve"
        effective_risk = 1.0

    # Cost estimate (DeepSeek-chat: ~$0.0014/1k input + $0.0028/1k output, but most calls < 1k each)
    tokens = api_resp.get("tokens", {})
    in_tok = int(tokens.get("prompt_tokens", 1500))
    out_tok = int(tokens.get("completion_tokens", 50))
    cost = (in_tok / 1000.0) * 0.0014 + (out_tok / 1000.0) * 0.0028

    verdict = GateVerdict(
        action=effective_action,
        risk_factor=effective_risk,
        confidence=float(api_resp.get("confidence", 0.5)),
        reason=str(api_resp.get("reason", ""))[:200],
        latency_ms=latency_ms,
        cost_estimate_usd=cost,
    )

    _log_gate_event({
        "event": "decided",
        "mode": mode,
        "ai_action": action,             # what AI suggested
        "effective_action": effective_action,  # what bot will actually do
        "verdict": asdict(verdict),
        "strategy": strategy, "symbol": symbol, "side": side, "regime": regime,
        "price": price, "sl": sl, "tp": tp,
        "tokens": tokens,
    }, log_path)

    return verdict


# Smoke test
if __name__ == "__main__":
    os.environ.setdefault("DEEPSEEK_GATE_ENABLED", "1")
    os.environ.setdefault("DEEPSEEK_GATE_MODE", "shadow")
    v = gate_signal(
        strategy="alt_trendline_touch_v1",
        symbol="BTCUSDT", side="long", regime="bull_chop",
        price=65000.0, sl=64200.0, tp=66500.0,
        recent_trades=[{"strategy": "att1", "side": "long", "pnl": 1.2}],
        context={"global_risk_mult": 0.7, "open_positions": 1},
    )
    print(f"Action: {v.action}  Reason: {v.reason}  Latency: {v.latency_ms:.0f}ms  Cost: ${v.cost_estimate_usd:.5f}")
