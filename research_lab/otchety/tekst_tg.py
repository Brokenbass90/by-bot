"""tekst_tg.py — подпись к карточке в Telegram (≤ 1024 символов), формат крипто-бота, по-русски, деньги со знаком."""
import datetime as dt
from stil import znak, prichina


def podpis(e):
    vr = dt.datetime.fromtimestamp(e["ts_ms"] / 1000, dt.timezone.utc).strftime("%d.%m %H:%M UTC")
    st = {"long": "ЛОНГ", "short": "ШОРТ"}.get(e.get("side"), "")
    sym = e.get("symbol") or e["sleeve"]; mode = "" if e["mode"] == "LIVE" else f" [{e['mode']}]"
    zag = " ".join(x for x in (sym, st, f"[{e['strategy']}]") if x) + f" · {e['venue']}{mode}"
    t = e["type"]
    if t == "ENTRY_FILLED":
        s = f"ВХОД {e['px']:g} × {e['qty']:g}" + (f" · стоп {e['stop_px']:g}" if e.get("stop_px") else "")
    elif t == "PROTECTION_BOUND":
        s = f"ЗАЩИТА стоит: стоп {e['stop_px']:g}"
    elif t == "STOP_MOVED":
        s = f"СТОП {e['stop_px_prev']:g} → {e['stop_px']:g}"
    elif t == "PARTIAL_FILL":
        s = f"ЧАСТИЧНО {e['qty']:g} из {e['qty_planned']:g} по {e['px']:g}"
    elif t == "EXIT_FILLED":
        s = f"ВЫХОД {e['px']:g} · {prichina(e['reason'])}" + (f" · итог {znak(e.get('net_pnl'), e['ccy'])}" if e.get("net_pnl") is not None else "")
    elif t == "FAILED_SAFE_FLAT":
        s = (f"НЕПОЛНАЯ КОРЗИНА {e.get('filled')}/{e.get('required')} → {prichina(e['reason'])}\n"
             f"итог теста {znak(e['net_pnl'], e['ccy'], 4)} · счёт плоский {'✓' if e['owner_flat'] else '✗'}")
    elif t == "NO_SEND":
        s = f"ОТПРАВКИ НЕ БЫЛО: {prichina(e['reason'])} · денег не тронуто"
    else:
        s = f"УЧЁТ: цена {znak(e['gross_pnl'], '', 4)} · комиссии {e['fees']:.4f} · фандинг {e['funding']:+.4f} · итог {znak(e['net_pnl'], e['ccy'], 4)}"
    return f"{zag}\n{s}\n{vr} · evidence {e['evidence_id']}"[:1024]
