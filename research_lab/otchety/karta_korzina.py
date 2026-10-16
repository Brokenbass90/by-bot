#!/usr/bin/env python3
"""karta_korzina.py — карточка многоногой корзины (KITY и будущие кросс-секции) и FAILED_SAFE_FLAT / NO_SEND. Вход — событие ReportEvent v1."""
import datetime as dt
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from stil import C, znak, OK, NET_, NEIZV, prichina


def risovat(e, put):
    legs = e.get("legs") or []
    vys = 2.7 + 0.32 * len(legs) + (1.0 if e.get("go_ms") else 0)
    fig = plt.figure(figsize=(8, vys), dpi=160); fig.patch.set_facecolor(C["bg"])
    H = vys; y = H - 0.3
    def t(x, yy, s, **kw):
        kw.setdefault("color", C["ink"]); kw.setdefault("fontsize", 10)
        fig.text(x / 8, yy / H, s, va="top", **kw)
    nazv = {"FAILED_SAFE_FLAT": "НЕПОЛНАЯ КОРЗИНА · БЕЗОПАСНО ЗАКРЫТО", "NO_SEND": "ОТПРАВКИ НЕ БЫЛО",
            "ACCOUNTING_FINAL": "КОРЗИНА ЗАКРЫТА"}.get(e["type"], e["type"])
    t(0.2, y, f"{e['sleeve']} · {e['strategy']} ({e['venue']})", fontsize=12, weight="bold")
    t(7.8, y, e["mode"], fontsize=9, color=C["muted"], weight="bold", ha="right"); y -= 0.38
    t(0.2, y, nazv, fontsize=11, color=C["exitc"] if e["type"] != "ACCOUNTING_FINAL" else C["ink"], weight="bold"); y -= 0.36
    if e["type"] == "FAILED_SAFE_FLAT":
        t(0.2, y, f"{e.get('filled', '?')}/{e.get('required', '?')} ног исполнено → {prichina(e['reason'])}", fontsize=9.5); y -= 0.3
    t(0.2, y, f"Итог: {znak(e.get('net_pnl'), e.get('ccy', ''), 4)}   (цена {znak(e.get('gross_pnl'), '', 4)} · комиссии {e.get('fees', 0):.4f}"
              f" · фандинг {e.get('funding', 0):+.4f})", fontsize=10); y -= 0.32
    if "owner_flat" in e:
        prot = [l["protected"] for l in legs if l.get("protected") is not None]
        t(0.2, y, f"Счёт плоский {OK if e['owner_flat'] else NET_}    Стоп на каждой исполненной ноге "
                  f"{OK if prot and all(prot) else NET_}    Отказов биржи {e.get('exchange_rejections', 0)}", fontsize=9.5); y -= 0.42
    # таблица ног
    kol = [0.2, 1.9, 2.8, 4.6, 5.6, 6.7]
    for x, z in zip(kol, ("нога", "сторона", "статус", "кол-во", "комиссия", "защита · +с")):
        t(x, y, z, fontsize=8.5, color=C["muted"])
    y -= 0.28
    for l in legs:
        ok = l["status"].startswith("FILLED")
        col = C["ink"] if ok else C["muted"]
        st = {"long": "ЛОНГ", "short": "ШОРТ"}.get(l.get("side"), "—")
        zashch = (OK if l["protected"] else NET_) if l.get("protected") is not None else "—"
        sec = f" · {l['after_go_ms'] / 1000:.0f}" if l.get("after_go_ms") is not None else ""
        for x, z in zip(kol, (l["symbol"], st, l["status"].replace("FILLED→CLOSED", "исполнена → закрыта"), f"{l['qty']:g}" if ok else "—", f"{l['fees']:.4f}" if ok else "—", zashch + sec)):
            t(x, y, z, fontsize=9, color=col)
        y -= 0.32
    if e.get("go_ms") and e.get("entry_deadline_ms"):                  # шкала времени: GO → отправки ног → дедлайн
        ax = fig.add_axes([0.2 / 8, (y - 0.75) / H, 7.4 / 8, 0.55 / H]); ax.set_facecolor(C["plot"])
        dl = (e["entry_deadline_ms"] - e["go_ms"]) / 1000
        xs = [l["after_go_ms"] / 1000 for l in legs if l.get("after_go_ms") is not None]
        ax.scatter(xs, [0] * len(xs), color=C["entry"], s=30, zorder=3)
        ax.axvline(0, color=C["muted"], lw=1); ax.axvline(dl, color=C["stop"], lw=1.4, ls="--")
        ax.text(0, 0.55, " GO", color=C["muted"], fontsize=7.5, va="top"); ax.text(dl, 0.55, f" дедлайн {dl:.0f} с", color=C["stop"], fontsize=7.5, va="top")
        ax.set_xlim(-2, max(dl, max(xs) if xs else 0) * 1.15); ax.set_ylim(-0.6, 0.6); ax.set_yticks([])
        ax.tick_params(colors=C["muted"], labelsize=7)
        for sp in ax.spines.values(): sp.set_color(C["spine"])
        y -= 1.0
    t(0.2, max(y, 0.35), f"evidence: {e['evidence_id']}   ·   {dt.datetime.fromtimestamp(e['ts_ms'] / 1000, dt.timezone.utc):%d.%m %H:%M UTC}",
      fontsize=7.5, color=C["muted"])
    fig.savefig(put, facecolor=C["bg"]); plt.close(fig); return put
