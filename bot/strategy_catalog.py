"""Machine-readable catalogue of the live strategy families.

Purpose
-------
The on-board AI (Telegram + web chat, via ``bot.ai_context``) previously only
saw a *runtime snapshot* (open positions, heartbeat, allocator status). It had
no idea how each strategy is configured or how its TP/SL works — so it could not
answer questions like "why is there a stop on the exchange but no take-profit?".

This module exposes, for each strategy family:
  * whether it is enabled for live trading (from ``ENABLE_*_TRADING`` env),
  * its risk multiplier (from ``*_RISK_MULT`` env),
  * a short, code-grounded description of its execution + TP/SL model,
  * the key tuning params (read live from env so the numbers are never stale).

It is **pure / read-only** — it reads ``os.environ`` and returns plain dicts and
strings. It never touches the trade path.

The structural TP/SL descriptions below are grounded in the actual code
(``strategies/*.py`` + the runner wiring in ``smart_pump_reversal_bot.py``):
runner-type families emit a TP ladder (``sig.tps``/``sig.tp_fracs``); for them
the bot intentionally places **only the stop** on the exchange and manages the
laddered take-profits itself (partial TP1 -> runner/trail to TP2, plus breakeven
and time-stop).
"""

from __future__ import annotations

import os
from typing import Any, Mapping


# exec_model values:
#   "runner_ladder" -> broker holds ONLY the stop; TP1 partial + runner/trail
#                      to TP2 + breakeven + time-stop are managed in-bot.
#   "single_tp"     -> a single fixed TP and SL are both placed on the exchange.
_FAMILIES: list[dict[str, Any]] = [
    {
        "key": "att1", "label": "ATT1 — trendline touch", "market": "crypto",
        "enable_env": "ENABLE_ATT1_TRADING", "risk_env": "ATT1_RISK_MULT",
        "exec_model": "runner_ladder",
        "tpsl": ("Runner. На бирже только стоп. Вход по касанию трендлайна; TP "
                 "лестницей (частичный TP1 -> раннер/трейлинг до TP2), breakeven "
                 "и time-stop ведёт бот."),
        "param_envs": ["ATT1_PIVOT_LEFT", "ATT1_PIVOT_RIGHT", "ATT1_MIN_R2",
                       "ATT1_TOUCH_ATR", "ATT1_DECISION_MIN_AGE_MIN",
                       "ATT1_MAX_OPEN_TRADES"],
    },
    {
        "key": "support_bounce", "label": "ASB1 — support bounce", "market": "crypto",
        "enable_env": "ENABLE_ASB1_TRADING", "risk_env": "ASB1_RISK_MULT",
        "exec_model": "runner_ladder",
        "tpsl": ("Runner. На бирже только стоп (~0.85*ATR). Отбой от поддержки; "
                 "TP1 ~60% позиции, затем раннер; time-stop ~576 баров 5m."),
        "param_envs": ["ASB1_SL_ATR_MULT", "ASB1_TP1_FRAC", "ASB1_TP2_BUFFER_PCT",
                       "ASB1_TIME_STOP_BARS_5M", "ASB1_REGIME_MAX_SLOPE_PCT",
                       "ASB1_MAX_OPEN_TRADES"],
    },
    {
        "key": "bounce1", "label": "BOUNCE1 — support bounce wrapper", "market": "crypto",
        "enable_env": "ENABLE_BOUNCE1_TRADING", "risk_env": "BOUNCE1_RISK_MULT",
        "exec_model": "runner_ladder",
        "tpsl": "Runner (live-обёртка alt_support_bounce_v1). На бирже только стоп.",
        "param_envs": ["BOUNCE1_MAX_OPEN_TRADES"],
    },
    {
        "key": "midterm", "label": "MTPB — BTC/ETH midterm pullback", "market": "crypto",
        "enable_env": "ENABLE_MIDTERM_TRADING", "risk_env": "MIDTERM_RISK_MULT",
        "exec_model": "runner_ladder",
        "tpsl": ("Runner. На бирже только стоп (~1.2*ATR). Откуп тренда BTC/ETH; "
                 "TP1 50% @1.2R, TP2 @2.6R, runner-exits + time-stop ~84 баров 5m. "
                 "Исторически самый защищённый рукав."),
        "param_envs": ["MTPB_TREND_EMA_SLOW", "MTPB_TREND_SLOPE_MIN_PCT",
                       "MTPB_SL_ATR_MULT", "MTPB_TP1_RR", "MTPB_TP2_RR",
                       "MTPB_TP1_FRAC", "MTPB_TIME_STOP_BARS_5M"],
    },
    {
        "key": "ivb1", "label": "IVB1 — impulse volume breakout", "market": "crypto",
        "enable_env": "ENABLE_IVB1_TRADING", "risk_env": "IVB1_RISK_MULT",
        "exec_model": "runner_ladder",
        "tpsl": ("Runner. На бирже только стоп (~0.75*ATR). Пробой на импульсном "
                 "объёме; цель RR~2.2, TP1 @1.1R, трейлинг с 1.1R, breakeven @1R "
                 "(lock 0.1R)."),
        "param_envs": ["IVB1_SL_ATR", "IVB1_RR", "IVB1_TP1_RR",
                       "IVB1_TRAIL_ACTIVATE_RR", "IVB1_BE_TRIGGER_RR",
                       "IVB1_BE_LOCK_RR", "IVB1_MAX_OPEN_TRADES"],
    },
    {
        "key": "flat", "label": "ARF1 — flat resistance fade", "market": "crypto",
        "enable_env": "ENABLE_FLAT_TRADING", "risk_env": "FLAT_RISK_MULT",
        "exec_model": "runner_ladder",
        "tpsl": ("Runner. На бирже только стоп. Фейд сопротивления во флэте. "
                 "TP1/TP2 ведёт бот по ARF1_*; если ARF1_TRAIL_ATR_MULT=0, "
                 "авто-трейлинг выключен. ВНИМАНИЕ: рукав требует отдельной "
                 "walk-forward проверки перед повышением риска."),
        "param_envs": ["FLAT_MAX_OPEN_TRADES", "ARF1_TP1_FRAC",
                       "ARF1_TRAIL_ATR_MULT", "ARF1_TIME_STOP_BARS_5M",
                       "ARF1_SL_ATR_MULT", "ARF1_TP2_BUFFER_PCT"],
    },
    {
        "key": "breakdown", "label": "Breakdown — inplay breakdown (short)", "market": "crypto",
        "enable_env": "ENABLE_BREAKDOWN_TRADING", "risk_env": "BREAKDOWN_RISK_MULT",
        "exec_model": "runner_ladder",
        "tpsl": ("Runner, short-only, gated на медвежий режим. На бирже только "
                 "стоп (~1.8*ATR). Цель — следующий уровень; time-stop ~24ч. "
                 "Дизайн здравый; минусил только из-за старого P0-бага (исправлен)."),
        "param_envs": ["BREAKDOWN_MAX_OPEN_TRADES", "BREAKDOWN_BREAKER_MIN_TRADES"],
    },
]


def _is_enabled(env: Mapping[str, str], key: str) -> bool:
    return str(env.get(key, "0")).strip() in ("1", "true", "True", "yes", "on")


def _risk_mult(env: Mapping[str, str], key: str) -> float | None:
    raw = env.get(key)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def build_strategy_catalog(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Return the live strategy catalogue derived from env + static models."""
    e = os.environ if env is None else env
    families: list[dict[str, Any]] = []
    for fam in _FAMILIES:
        enabled = _is_enabled(e, fam["enable_env"])
        risk = _risk_mult(e, fam["risk_env"])
        params = {p: e.get(p) for p in fam.get("param_envs", []) if e.get(p) is not None}
        families.append(
            {
                "key": fam["key"],
                "label": fam["label"],
                "market": fam["market"],
                "enabled": enabled,
                "risk_mult": risk,
                # shadow = enabled but zero risk (telemetry only)
                "shadow": bool(enabled and (risk is not None) and risk == 0.0),
                "exec_model": fam["exec_model"],
                "tpsl_model": fam["tpsl"],
                "params": params,
            }
        )
    active = [f for f in families if f["enabled"] and not f["shadow"]]
    return {
        "note": ("runner_ladder = биржа держит ТОЛЬКО стоп; тейки (TP1 частичный + "
                 "раннер/трейлинг до TP2) + breakeven + time-stop исполняет сам бот. "
                 "single_tp = и TP, и SL стоят на бирже."),
        "active_count": len(active),
        "active_keys": [f["key"] for f in active],
        "families": families,
    }


def strategy_catalog_prompt_lines(env: Mapping[str, str] | None = None) -> list[str]:
    """Human-readable prompt lines so the AI can answer config/TP-SL questions."""
    cat = build_strategy_catalog(env)
    lines = [
        "STRATEGY CATALOG (live config + TP/SL model): " + str(cat.get("note")) + "\n",
        f"  active={cat.get('active_count')} keys={','.join(cat.get('active_keys') or [])}\n",
    ]
    for fam in cat.get("families", []):
        state = "ACTIVE" if (fam["enabled"] and not fam["shadow"]) else (
            "SHADOW" if fam["shadow"] else "off")
        params = " ".join(f"{k}={v}" for k, v in (fam.get("params") or {}).items())
        lines.append(
            f"  - {fam['label']} [{state}] risk_mult={fam['risk_mult']} "
            f"model={fam['exec_model']}: {fam['tpsl_model']}"
            + (f" | params: {params}" if params else "")
            + "\n"
        )
    return lines
