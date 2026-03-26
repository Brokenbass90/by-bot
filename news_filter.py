from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


@dataclass
class NewsEvent:
    event_id: str
    ts_utc: int
    country: str
    currency: str
    instrument_scope: str
    title: str
    impact: str
    source: str
    blackout_before_min: int
    blackout_after_min: int
    notes: str = ""


def _norm_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def load_news_events(csv_path: str | Path) -> list[NewsEvent]:
    p = Path(csv_path)
    if not p.exists():
        return []
    out: list[NewsEvent] = []
    with p.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for row in rd:
            try:
                out.append(
                    NewsEvent(
                        event_id=str(row.get("event_id") or "").strip(),
                        ts_utc=int(float(row.get("ts_utc") or 0)),
                        country=str(row.get("country") or "").strip().upper(),
                        currency=str(row.get("currency") or "").strip().upper(),
                        instrument_scope=str(row.get("instrument_scope") or "").strip().upper(),
                        title=str(row.get("title") or "").strip(),
                        impact=str(row.get("impact") or "").strip().lower(),
                        source=str(row.get("source") or "").strip(),
                        blackout_before_min=int(float(row.get("blackout_before_min") or 0)),
                        blackout_after_min=int(float(row.get("blackout_after_min") or 0)),
                        notes=str(row.get("notes") or "").strip(),
                    )
                )
            except Exception:
                continue
    return out


def load_news_policy(json_path: str | Path) -> dict[str, Any]:
    p = Path(json_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _symbol_scopes(symbol: str) -> set[str]:
    sym = _norm_symbol(symbol)
    scopes: set[str] = set()
    if len(sym) == 6 and sym.isalpha():
        base = sym[:3]
        quote = sym[3:]
        scopes |= {"FX", f"FX:{base}", f"FX:{quote}", f"FX:{base},{quote}", f"FX:{quote},{base}"}
        return scopes
    if sym == "XAUUSD":
        scopes |= {"METALS", "FX:USD", "METALS:XAUUSD", "XAUUSD"}
        return scopes
    if sym.endswith("USDT"):
        base = sym[:-4]
        scopes |= {"CRYPTO", f"CRYPTO:{base}", f"CRYPTO:{sym}"}
        return scopes
    if sym.isalpha() and 1 <= len(sym) <= 5:
        scopes |= {"EQUITIES", "EQUITIES:ALL", f"EQUITIES:{sym}"}
        return scopes
    scopes.add(sym)
    return scopes


def _strategy_policy(policy: dict[str, Any], strategy_name: str) -> dict[str, Any]:
    strategies = policy.get("strategies") if isinstance(policy, dict) else None
    if isinstance(strategies, dict):
        item = strategies.get(strategy_name)
        if isinstance(item, dict):
            return item
    return {}


def is_news_blocked(
    *,
    symbol: str,
    ts_utc: int,
    strategy_name: str,
    events: Iterable[NewsEvent],
    policy: Optional[dict[str, Any]] = None,
) -> tuple[bool, str]:
    pol = policy or {}
    if not bool(pol.get("enabled", True)):
        return False, ""

    blocked_impacts = {str(x).strip().lower() for x in (pol.get("impact_levels_blocked") or ["high"])}
    default_before = int(pol.get("default_before_min", 20))
    default_after = int(pol.get("default_after_min", 30))
    strat_pol = _strategy_policy(pol, strategy_name)
    scopes = _symbol_scopes(symbol)

    if isinstance(strat_pol.get("markets"), list) and strat_pol["markets"]:
        markets = {str(x).strip().upper() for x in strat_pol["markets"]}
        if not any(s.split(":")[0] in markets or s in markets for s in scopes):
            return False, ""

    for ev in events:
        if ev.impact not in blocked_impacts:
            continue
        ev_scope = str(ev.instrument_scope or "").strip().upper()
        ev_currency = str(ev.currency or "").strip().upper()
        if ev_scope and ev_scope not in scopes and ev_scope not in {"ALL", "EQUITIES:ALL"}:
            if ev_currency and not any(sc.endswith(f":{ev_currency}") or f":{ev_currency}," in sc or sc.endswith(f",{ev_currency}") for sc in scopes):
                continue
        before_min = int(strat_pol.get("before_min", ev.blackout_before_min or default_before))
        after_min = int(strat_pol.get("after_min", ev.blackout_after_min or default_after))
        start_ts = int(ev.ts_utc) - before_min * 60
        end_ts = int(ev.ts_utc) + after_min * 60
        if start_ts <= int(ts_utc) <= end_ts:
            title = ev.title or ev.event_id or "event"
            return True, f"{title} [{ev.impact}] blackout until {end_ts}"
    return False, ""
