#!/usr/bin/env python3
"""fx_kontrakt_v1.py — контракт данных и издержек FX/CFD/Gold (Factory V3, слой 7). 13.10.2026. ДИЗАЙН + FIXTURES, без PnL.

Почему так: 30.09 FX/Gold закрыт на ИЗДЕРЖКАХ (53 пункта; ночной дрейф +2.28 bps валовых — не исполним), а MT5 дал дефект
времени. Поэтому адаптер начинается не с сигналов, а с правды исполнения: bid/ask, спред по сессиям, своп с утроением,
комиссия, мин. стоп, лот/пункт, время сервера ↔ UTC с DST, торговая неделя и гэпы.

Время: торговый день FX закрывается в 17:00 America/New_York (ролловер, начисление свопа). Сервер MT5 обычно «NY+7»:
UTC+2 зимой США, UTC+3 летом США → полночь сервера = 17:00 NY. США и Европа переводят часы в разные даты (март/октябрь–ноябрь),
поэтому только zoneinfo, никаких фиксированных смещений.

ЗНАЧЕНИЯ В FIXTURES — НЕ ПРАВДА БРОКЕРА. Перед любым исследованием их заменяет атлас реального брокера (снимки bid/ask и
спецификации символов), иначе адаптер отказывается считать издержки (fixture=True ⇒ OshibkaFX в boevom-режиме).
"""
import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York"); LON = ZoneInfo("Europe/London"); UTC = dt.timezone.utc


class OshibkaFX(Exception):
    pass


@dataclass(frozen=True)
class Instrument:
    sym: str
    point: float                # минимальный шаг цены
    kontrakt: float             # единиц базового актива на 1 лот
    kotirovka: str              # валюта котировки (USD / JPY)
    lot_shag: float
    lot_min: float
    min_stop_pt: int            # минимальная дистанция стопа, пунктов
    komissiya_usd_lot_storona: float
    svop_long_pt: float         # пунктов за лот за ночь (знак: + начисление, − списание)
    svop_short_pt: float
    utroennyy_den: int          # weekday (0=пн) когда начисляется тройной своп (ролловер на этот день)
    fixture: bool = True


FIXTURES = {   # иллюстративные значения для тестов и дизайна; fixture=True
    "XAUUSD": Instrument("XAUUSD", 0.01, 100, "USD", 0.01, 0.01, 50, 3.5, -55.0, 25.0, 2),
    "EURUSD": Instrument("EURUSD", 0.00001, 100_000, "USD", 0.01, 0.01, 10, 3.5, -7.0, 2.5, 2),
    "GBPUSD": Instrument("GBPUSD", 0.00001, 100_000, "USD", 0.01, 0.01, 10, 3.5, -5.0, 1.0, 2),
    "USDJPY": Instrument("USDJPY", 0.001, 100_000, "JPY", 0.01, 0.01, 10, 3.5, 12.0, -25.0, 2),
}


# ---------- время ----------
def server_v_utc(ts_server_naive: dt.datetime):
    """Время сервера «NY+7» → UTC. Сервер = NY + 7 ч круглый год (полночь сервера = 17:00 NY)."""
    ny = (ts_server_naive - dt.timedelta(hours=7)).replace(tzinfo=NY)
    return ny.astimezone(UTC)


def rollovery(t_in: dt.datetime, t_out: dt.datetime):
    """Список моментов ролловера (17:00 NY) строго внутри (t_in, t_out]."""
    out = []; d = t_in.astimezone(NY).date() - dt.timedelta(days=1)
    while True:
        r = dt.datetime.combine(d, dt.time(17, 0), NY).astimezone(UTC)
        if r > t_out: break
        if r > t_in and r.astimezone(NY).weekday() < 5: out.append(r)
        d += dt.timedelta(days=1)
    return out


def rynok_otkryt(t: dt.datetime):
    """FX: открыт с вс 17:00 NY до пт 17:00 NY."""
    n = t.astimezone(NY); wd, h = n.weekday(), n.hour + n.minute / 60
    if wd == 5: return False
    if wd == 6: return h >= 17
    if wd == 4: return h < 17
    return True


def sessiya(t: dt.datetime):
    """Ликвидные сессии по местному времени (с DST каждого города): ASIA / LONDON / OVERLAP / NY / CLOSED."""
    if not rynok_otkryt(t): return "CLOSED"
    l, n = t.astimezone(LON), t.astimezone(NY)
    lon = 8 <= l.hour < 17; ny = 8 <= n.hour < 17
    return "OVERLAP" if lon and ny else ("LONDON" if lon else ("NY" if ny else "ASIA"))


# ---------- деньги ----------
def stoimost_punkta_usd(ins: Instrument, cena: float):
    """USD за 1 пункт на 1 лот."""
    v = ins.point * ins.kontrakt
    return v if ins.kotirovka == "USD" else v / cena            # USDJPY: стоимость в JPY → USD


def izderzhki_kruga_usd(ins: Instrument, vhod: dict, vyhod: dict, loty: float, napravlenie: int, boevoy=False):
    """vhod/vyhod: {'t': datetime UTC, 'bid', 'ask'}; napravlenie +1 лонг / −1 шорт.
    Спред (вход по ask/bid, выход по bid/ask против середины) + комиссия×2 + свопы (утроение в utroennyy_den)."""
    if boevoy and ins.fixture: raise OshibkaFX(f"{ins.sym}: значения-fixtures, нужен атлас брокера")
    for q in (vhod, vyhod):
        if not q["ask"] > q["bid"] > 0: raise OshibkaFX("перекрещенная/пустая котировка")
        if not rynok_otkryt(q["t"]): raise OshibkaFX(f"котировка в закрытом рынке {q['t']}")
    if round(loty / ins.lot_shag, 9) % 1 or loty < ins.lot_min: raise OshibkaFX("объём не кратен шагу лота / меньше минимума")
    pt_usd = stoimost_punkta_usd(ins, (vyhod["bid"] + vyhod["ask"]) / 2)
    sprred_pt = ((vhod["ask"] - vhod["bid"]) / 2 + (vyhod["ask"] - vyhod["bid"]) / 2) / ins.point
    spred = sprred_pt * pt_usd * loty
    noch = sum(3 if r.astimezone(NY).weekday() == ins.utroennyy_den else 1 for r in rollovery(vhod["t"], vyhod["t"]))
    svop_pt = (ins.svop_long_pt if napravlenie > 0 else ins.svop_short_pt) * noch
    svop = -svop_pt * pt_usd * loty                               # положительный своп уменьшает издержки
    kom = 2 * ins.komissiya_usd_lot_storona * loty
    return dict(spred_usd=round(spred, 4), komissiya_usd=round(kom, 4), svop_usd=round(svop, 4), nochey=noch,
                itogo_usd=round(spred + kom + svop, 4))


def proverit_kotirovki(rows, ins: Instrument):
    """rows: [(t UTC, bid, ask)]. Дефекты: перекрещено, время назад, котировки в закрытом рынке, дыры внутри сессии > 30 мин."""
    plohie = sum(1 for _, b, a in rows if not a > b > 0)
    nazad = sum(1 for (t1, *_), (t2, *_) in zip(rows, rows[1:]) if t2 <= t1)
    zakryt = sum(1 for t, *_ in rows if not rynok_otkryt(t))
    dyry = sum(1 for (t1, *_), (t2, *_) in zip(rows, rows[1:]) if (t2 - t1) > dt.timedelta(minutes=30) and rynok_otkryt(t1) and rynok_otkryt(t2)
               and not any(not rynok_otkryt(t1 + dt.timedelta(minutes=m)) for m in range(0, int((t2 - t1).total_seconds() // 60), 15)))
    return dict(perekreshcheno=plohie, nazad=nazad, v_zakrytom_rynke=zakryt, dyr_v_sessii=dyry)
