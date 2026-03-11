from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol

from .types import BacktestSummary, Candle, Signal, Trade


class Strategy(Protocol):
    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        ...


@dataclass
class EngineConfig:
    pip_size: float = 0.0001
    spread_pips: float = 1.2
    swap_long_pips_per_day: float = -0.2
    swap_short_pips_per_day: float = -0.2
    risk_per_trade_pct: float = 0.005


def _pips(side: str, entry: float, exit_: float, pip_size: float) -> float:
    d = (exit_ - entry) / max(1e-12, pip_size)
    return d if side == "long" else -d


def run_backtest(candles: List[Candle], strategy: Strategy, cfg: EngineConfig) -> tuple[List[Trade], BacktestSummary]:
    trades: List[Trade] = []
    if not candles:
        return trades, BacktestSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, notes="empty data")

    pos = None
    # pos: dict(side,entry,sl,tp,entry_ts,entry_i,last_day,swap_pips,risk_pips)
    eq = 0.0
    curve = [0.0]
    eq_mult = 1.0

    for i, c in enumerate(candles):
        if pos is not None:
            cur_day = int(c.ts // 86400)
            if cur_day > pos["last_day"]:
                d = cur_day - pos["last_day"]
                pos["last_day"] = cur_day
                pos["swap_pips"] += d * (cfg.swap_long_pips_per_day if pos["side"] == "long" else cfg.swap_short_pips_per_day)

            sl_hit = (c.l <= pos["sl"]) if pos["side"] == "long" else (c.h >= pos["sl"])
            tp_hit = (c.h >= pos["tp"]) if pos["side"] == "long" else (c.l <= pos["tp"])

            if sl_hit or tp_hit:
                # conservative: SL wins on same bar
                exit_price = pos["sl"] if sl_hit else pos["tp"]
                gross = _pips(pos["side"], pos["entry"], exit_price, cfg.pip_size)
                net = gross - cfg.spread_pips + pos["swap_pips"]
                risk_pips = max(1e-12, float(pos.get("risk_pips", 0.0)))
                r_multiple = net / risk_pips if risk_pips > 0 else 0.0
                eq += net
                eq_mult = max(0.0, eq_mult * (1.0 + float(cfg.risk_per_trade_pct) * r_multiple))
                trades.append(
                    Trade(
                        side=pos["side"],
                        entry_ts=pos["entry_ts"],
                        exit_ts=c.ts,
                        entry_price=pos["entry"],
                        exit_price=exit_price,
                        pnl_pips=gross,
                        net_pips=net,
                        reason="SL" if sl_hit else "TP",
                        risk_pips=risk_pips,
                        r_multiple=r_multiple,
                    )
                )
                pos = None

        if pos is None:
            sig = strategy.maybe_signal(candles, i)
            if sig is not None and sig.side in {"long", "short"}:
                risk_pips = abs(_pips(sig.side, float(sig.entry), float(sig.sl), cfg.pip_size))
                if risk_pips <= 0:
                    continue
                pos = {
                    "side": sig.side,
                    "entry": float(sig.entry),
                    "sl": float(sig.sl),
                    "tp": float(sig.tp),
                    "entry_ts": c.ts,
                    "entry_i": i,
                    "last_day": int(c.ts // 86400),
                    "swap_pips": 0.0,
                    "risk_pips": float(risk_pips),
                }

        curve.append(eq)

    # force close on last close
    if pos is not None:
        last = candles[-1]
        gross = _pips(pos["side"], pos["entry"], last.c, cfg.pip_size)
        net = gross - cfg.spread_pips + pos["swap_pips"]
        risk_pips = max(1e-12, float(pos.get("risk_pips", 0.0)))
        r_multiple = net / risk_pips if risk_pips > 0 else 0.0
        eq += net
        eq_mult = max(0.0, eq_mult * (1.0 + float(cfg.risk_per_trade_pct) * r_multiple))
        trades.append(
            Trade(
                side=pos["side"],
                entry_ts=pos["entry_ts"],
                exit_ts=last.ts,
                entry_price=pos["entry"],
                exit_price=last.c,
                pnl_pips=gross,
                net_pips=net,
                reason="EOP",
                risk_pips=risk_pips,
                r_multiple=r_multiple,
            )
        )
        curve.append(eq)

    wins = [t.net_pips for t in trades if t.net_pips > 0]
    losses = [t.net_pips for t in trades if t.net_pips < 0]
    gross = sum(t.pnl_pips for t in trades)
    net = sum(t.net_pips for t in trades)
    peak = curve[0]
    max_dd = 0.0
    for x in curve:
        if x > peak:
            peak = x
        dd = peak - x
        if dd > max_dd:
            max_dd = dd

    summary = BacktestSummary(
        trades=len(trades),
        winrate=(len(wins) / len(trades) * 100.0) if trades else 0.0,
        net_pips=net,
        gross_pips=gross,
        max_dd_pips=max_dd,
        avg_win_pips=(sum(wins) / len(wins)) if wins else 0.0,
        avg_loss_pips=(sum(losses) / len(losses)) if losses else 0.0,
        last_equity_pips=curve[-1] if curve else 0.0,
        sum_r=sum(t.r_multiple for t in trades),
        return_pct_est=(eq_mult - 1.0) * 100.0,
    )
    return trades, summary
