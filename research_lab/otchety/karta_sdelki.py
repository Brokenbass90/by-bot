#!/usr/bin/env python3
"""karta_sdelki.py — карточка сделки PNG для Telegram/веба (16.10.2026, Claude). Чистая функция: события сделки + бары → PNG.
Не ходит в сеть, не знает ключей; бары и события ей передаёт исполнитель (Codex) из своего журнала.

Событие сделки (TradeCard v1):
  sleeve, strategy, venue, symbol, side ("long"/"short"), qty, ccy,
  entry {t_ms, px}, stop_px, targets [px...] (опц.), exit {t_ms, px, reason} | None (позиция открыта),
  fees, funding, pnl_net | None, status ("OPEN"/"CLOSED"), mark_px (для открытой), tf ("1d"/"1h")
bars: [[t_ms, o, h, l, c], ...]  — заканчиваются не раньше выхода (или «сейчас» для открытой).
"""
import datetime as dt
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

C = dict(bg="#FFFFFF", ink="#1F2328", muted="#6E7781", grid="#EAEEF2", up="#2F7D5B", down="#B4473A",
         entry="#1F2328", stop="#B4473A", target="#2F7D5B", exitc="#3B6FB6")


def _fmt(x, ccy):
    return f"{x:,.2f} {ccy}" if abs(x) >= 1 else f"{x:.4f} {ccy}"


def risovat(sdelka, bars, put):
    s, ccy = sdelka, sdelka.get("ccy", "USD")
    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=160)
    fig.patch.set_facecolor(C["bg"]); ax.set_facecolor(C["bg"])
    w = 0.6
    for k, (t, o, h, l, c) in enumerate(bars):
        col = C["up"] if c >= o else C["down"]
        ax.plot([k, k], [l, h], color=col, lw=1)
        ax.add_patch(Rectangle((k - w / 2, min(o, c)), w, max(abs(c - o), 1e-9), facecolor=col, edgecolor=col, lw=0))
    ts = [b[0] for b in bars]
    def x_of(t):
        return min(range(len(ts)), key=lambda i: abs(ts[i] - t))
    n = len(bars)
    e = s["entry"]; xe = x_of(e["t_ms"])
    def uroven(y, col, tekst, stil="-"):
        ax.hlines(y, -1, n - 0.3, color=col, lw=1.2, ls=stil, alpha=0.9)
        ax.text(n + 0.2, y, f" {tekst} {y:,.2f}", va="center", ha="left", fontsize=8.5, color=C["ink"])
    uroven(e["px"], C["entry"], "Вход")
    if s.get("stop_px"): uroven(s["stop_px"], C["stop"], "Стоп", "--")
    for i, tp in enumerate(s.get("targets") or []): uroven(tp, C["target"], f"Цель {i + 1}", ":")
    ax.scatter([xe], [e["px"]], s=70, marker="^" if s["side"] == "long" else "v", color=C["entry"], zorder=5,
               edgecolors="white", linewidths=1.5)
    if s.get("exit"):
        xx = x_of(s["exit"]["t_ms"]); uroven(s["exit"]["px"], C["exitc"], "Выход")
        ax.scatter([xx], [s["exit"]["px"]], s=70, marker="X", color=C["exitc"], zorder=5, edgecolors="white", linewidths=1.5)
    ax.set_xlim(-1, n + 7)
    step = max(1, n // 6)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([dt.datetime.fromtimestamp(ts[i] / 1000, dt.timezone.utc).strftime("%d.%m") for i in range(0, n, step)],
                       fontsize=8, color=C["muted"])
    ax.tick_params(axis="y", labelsize=8, colors=C["muted"]); ax.grid(axis="y", color=C["grid"], lw=0.8)
    for sp in ax.spines.values(): sp.set_visible(False)
    # шапка: что, где, итог — текстом (знак и стрелка, не только цвет)
    napr = "ЛОНГ" if s["side"] == "long" else "ШОРТ"
    zag = f"{s['symbol']} · {napr} · {s['strategy']} ({s['venue']})"
    if s["status"] == "CLOSED" and s.get("pnl_net") is not None:
        p = s["pnl_net"]; pct = p / (e["px"] * s["qty"]) * 100
        itog = f"{'▲ +' if p >= 0 else '▼ −'}{_fmt(abs(p), ccy)} ({pct:+.2f}%) · закрыта: {s['exit'].get('reason', '')}"
    else:
        m = s.get("mark_px", bars[-1][4]); p = (m - e["px"]) * s["qty"] * (1 if s["side"] == "long" else -1)
        risk = abs(e["px"] - s["stop_px"]) * s["qty"] if s.get("stop_px") else None
        itog = f"ОТКРЫТА · текущий {'▲ +' if p >= 0 else '▼ −'}{_fmt(abs(p), ccy)}" + (f" · риск до стопа {_fmt(risk, ccy)}" if risk else "")
    fig.text(0.02, 0.965, zag, fontsize=11.5, weight="bold", color=C["ink"], va="top")
    fig.text(0.02, 0.905, itog, fontsize=10, color=C["ink"], va="top")
    det = f"кол-во {s['qty']} · вход {_fmt(e['px'], ccy)} · комиссии {_fmt(s.get('fees', 0), ccy)} · фандинг {_fmt(s.get('funding', 0), ccy)}"
    fig.text(0.02, 0.855, det, fontsize=8.5, color=C["muted"], va="top")
    if s.get("demo"): fig.text(0.98, 0.965, "ДЕМО", fontsize=9, color=C["muted"], ha="right", va="top", weight="bold")
    fig.subplots_adjust(left=0.07, right=0.84, top=0.80, bottom=0.08)
    fig.savefig(put, facecolor=C["bg"]); plt.close(fig)
    return put
