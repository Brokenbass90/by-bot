#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import csv
import time
import sqlite3
from dataclasses import dataclass
from typing import List, Tuple, Optional


@dataclass
class ReportResult:
    text: str
    csv_path: Optional[str]
    png_path: Optional[str]


def _fetch_closes(db_path: str, since_ts: int) -> List[Tuple[int, float]]:
    rows: List[Tuple[int, float]] = []
    if not os.path.exists(db_path):
        return rows
    try:
        with sqlite3.connect(db_path) as con:
            cur = con.execute(
                "SELECT ts, pnl FROM trade_events WHERE event='CLOSE' AND pnl IS NOT NULL AND ts>=? ORDER BY ts ASC",
                (int(since_ts),),
            )
            rows = [(int(ts), float(pnl)) for ts, pnl in cur.fetchall()]
    except Exception:
        return []
    return rows


def _fetch_strategy_stats(db_path: str, since_ts: int) -> List[dict]:
    rows: List[dict] = []
    if not os.path.exists(db_path):
        return rows
    try:
        with sqlite3.connect(db_path) as con:
            cur = con.execute(
                """
                SELECT COALESCE(NULLIF(strategy, ''), 'unknown') AS strategy,
                       COUNT(*) AS closes,
                       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) AS losses,
                       SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) AS gross_win,
                       ABS(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END)) AS gross_loss,
                       SUM(pnl) AS net
                  FROM trade_events
                 WHERE event='CLOSE' AND pnl IS NOT NULL AND ts>=?
                 GROUP BY COALESCE(NULLIF(strategy, ''), 'unknown')
                """,
                (int(since_ts),),
            )
            for strategy, closes, wins, losses, gross_win, gross_loss, net in cur.fetchall():
                rows.append(
                    {
                        "strategy": str(strategy or "unknown"),
                        "closes": int(closes or 0),
                        "wins": int(wins or 0),
                        "losses": int(losses or 0),
                        "gross_win": float(gross_win or 0.0),
                        "gross_loss": float(gross_loss or 0.0),
                        "net": float(net or 0.0),
                    }
                )
    except Exception:
        return []
    return rows


def _format_strategy_breakdown(rows: List[dict], limit: int = 8) -> List[str]:
    if not rows:
        return []
    ordered = sorted(
        rows,
        key=lambda item: (
            -int(item.get("closes", 0) or 0),
            -abs(float(item.get("net", 0.0) or 0.0)),
            str(item.get("strategy") or ""),
        ),
    )
    out: List[str] = []
    for item in ordered[: max(1, int(limit))]:
        closes = int(item.get("closes", 0) or 0)
        wins = int(item.get("wins", 0) or 0)
        gross_loss = float(item.get("gross_loss", 0.0) or 0.0)
        gross_win = float(item.get("gross_win", 0.0) or 0.0)
        winrate = (wins / closes * 100.0) if closes > 0 else 0.0
        pf = (gross_win / gross_loss) if gross_loss > 1e-12 else float("inf")
        out.append(
            f"- {item.get('strategy')}: t={closes} wr={winrate:.0f}% pf={pf:.2f} net={float(item.get('net', 0.0) or 0.0):+.2f}"
        )
    if len(ordered) > len(out):
        out.append(f"- ... +{len(ordered) - len(out)} more")
    return out


def _write_csv(rows: List[Tuple[int, float]], out_path: str) -> Optional[str]:
    if not rows:
        return None
    try:
        with open(out_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ts", "pnl", "cum_pnl"])
            cum = 0.0
            for ts, pnl in rows:
                cum += pnl
                w.writerow([ts, pnl, cum])
        return out_path
    except Exception:
        return None


def _plot_equity(rows: List[Tuple[int, float]], out_path: str) -> Optional[str]:
    if not rows:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ts = []
        cum = []
        s = 0.0
        for t, pnl in rows:
            s += pnl
            ts.append(t)
            cum.append(s)
        plt.figure(figsize=(8, 3.6))
        plt.plot(ts, cum, linewidth=1.6)
        plt.title("Cumulative PnL")
        plt.xlabel("timestamp")
        plt.ylabel("USDT")
        plt.tight_layout()
        plt.savefig(out_path, dpi=140)
        plt.close()
        return out_path
    except Exception:
        return None


def generate_report(db_path: str, since_ts: int, out_dir: str, tag: str) -> ReportResult:
    rows = _fetch_closes(db_path, since_ts)
    strategy_stats = _fetch_strategy_stats(db_path, since_ts)
    now_ts = int(time.time())
    since_iso = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(int(since_ts)))
    as_of_iso = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(now_ts))
    if not rows:
        return ReportResult(
            text=f"{tag} report\nsince={since_iso}\nas_of={as_of_iso}\nнет сделок за период.",
            csv_path=None,
            png_path=None,
        )

    wins = sum(1 for _, pnl in rows if pnl > 0)
    losses = sum(1 for _, pnl in rows if pnl < 0)
    total = len(rows)
    winrate = (wins / total * 100.0) if total else 0.0
    sum_win = sum(pnl for _, pnl in rows if pnl > 0)
    sum_loss = abs(sum(pnl for _, pnl in rows if pnl < 0))
    pf = (sum_win / sum_loss) if sum_loss > 0 else float("inf")
    net = sum(pnl for _, pnl in rows)

    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, f"bybot_{tag}.csv")
    png_path = os.path.join(out_dir, f"bybot_{tag}.png")
    csv_out = _write_csv(rows, csv_path)
    png_out = _plot_equity(rows, png_path)
    strategy_lines = _format_strategy_breakdown(strategy_stats)

    txt = (
        f"{tag} report\n"
        f"since={since_iso} | as_of={as_of_iso}\n"
        f"trades={total} winrate={winrate:.1f}% pf={pf:.2f}\n"
        f"net_pnl={net:+.2f} USDT"
    )
    if strategy_lines:
        txt += "\nby_strategy:\n" + "\n".join(strategy_lines)
    return ReportResult(text=txt, csv_path=csv_out, png_path=png_out)


def since_days(days: int) -> int:
    return int(time.time()) - int(days) * 86400
