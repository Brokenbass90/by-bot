#!/usr/bin/env python3
"""polymarket_stend.py — тестовый стенд Polymarket «как будто мы в прошлом» (DATA_ONLY, без ставок и кошельков).

Идея: стратегия в момент решения T видит ТОЛЬКО то, что было известно в T:
  - рынки, открытые на T (createdAt/startDate ≤ T < closedTime);
  - цены токенов с меткой t ≤ T (история CLOB prices-history);
  - никаких итогов, финальных объёмов и закрытия.
Итог рынка открывается стенду только при расчёте сделки после closedTime.

Входные данные (поставка Codex, ZAPROS_CODEX_POLYMARKET_DANNYE_2026_10_18.md):
  markets.jsonl — одна строка = один закрытый рынок Gamma API (поля читаются терпимо: outcomes / clobTokenIds /
                  outcomePrices могут быть JSON-строками);
  prices/<token_id>.json — ответ CLOB prices-history: {"history": [{"t": unix_sec, "p": price}, ...]}.
Если формат поставки окажется другим — меняется только загрузчик, стенд и стратегии нет.

Издержки: полспреда + комиссия тейкера, в долях цены исхода (по умолчанию 0.01 и 0.0 — prereg задаёт фактические).
"""
from __future__ import annotations

import bisect, json, math, re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable


def _ts(x) -> int | None:
    """ISO-строка или unix → unix-секунды."""
    if x is None or x == "":
        return None
    if isinstance(x, (int, float)):
        return int(x / 1000) if x > 1e11 else int(x)
    s = str(x).strip().replace("Z", "+00:00").replace(" ", "T", 1)
    if re.search(r"[+-]\d\d$", s):                     # «+00» → «+00:00» (формат closedTime Gamma API)
        s += ":00"
    s = re.sub(r"\.(\d{1,6})(?=[+-]|$)", lambda m: "." + m.group(1).ljust(6, "0"), s)   # «.24» → «.240000»
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return int(d.timestamp())


def _spisok(x):
    if isinstance(x, str):
        try:
            return json.loads(x)
        except json.JSONDecodeError:
            return []
    return list(x or [])


@dataclass
class Rynok:
    id: str
    vopros: str
    kategoriya: str
    otkryt: int                      # с какого момента рынок существует
    zakryt: int                      # closedTime — после него итог известен (стратегии НЕ видно)
    plan: int                        # endDate — плановое закрытие, известно заранее
    ishody: list[str]
    tokeny: list[str]
    pobeditel: int | None            # индекс выигравшего исхода (только для расчёта!)
    gruppa: str | None = None        # negRisk / событие — для проверки «сумма < 1»
    ceny: dict[str, tuple[list[int], list[float]]] = field(default_factory=dict)


def zagruzit(katalog: Path) -> list[Rynok]:
    out = []
    for s in (katalog / "markets.jsonl").read_text().splitlines():
        if not s.strip():
            continue
        m = json.loads(s)
        ishody = _spisok(m.get("outcomes")); tokeny = [str(t) for t in _spisok(m.get("clobTokenIds"))]
        fin = [float(x) for x in _spisok(m.get("outcomePrices"))]
        pob = None
        if fin and len(fin) == len(ishody) and max(fin) >= 0.99:   # закрытый рынок с однозначным итогом
            pob = int(max(range(len(fin)), key=lambda i: fin[i]))
        zak = _ts(m.get("closedTime")); zak = zak if zak is not None else _ts(m.get("endDate"))
        otk = _ts(m.get("startDate")); otk = otk if otk is not None else _ts(m.get("createdAt"))
        if not (ishody and tokeny) or zak is None or otk is None or len(ishody) != len(tokeny):
            continue
        ev = m.get("events") or []
        gr = (ev[0].get("id") if ev and isinstance(ev[0], dict) else None) or m.get("negRiskMarketID")
        plan = _ts(m.get("endDate")); plan = plan if plan is not None else zak
        r = Rynok(str(m.get("id")), m.get("question", ""), str(m.get("category") or ""), otk, zak, plan, ishody, tokeny, pob,
                  str(gr) if gr else None)
        for t in tokeny:
            f = katalog / "prices" / f"{t}.json"
            if f.exists():
                h = json.loads(f.read_text()).get("history") or []
                h = sorted((int(x["t"]), float(x["p"])) for x in h)
                r.ceny[t] = ([a for a, _ in h], [b for _, b in h])
        out.append(r)
    return out


class Proshloe:
    """Окно в прошлое: всё, что стратегия может спросить в момент T."""

    def __init__(self, rynki: list[Rynok], T: int):
        self._r = rynki; self.T = T

    def otkrytye(self) -> Iterable[Rynok]:
        for r in self._r:
            if r.otkryt <= self.T < r.zakryt:
                yield r

    def cena(self, r: Rynok, i_ishoda: int, maks_vozrast_s: int = 6 * 3600) -> float | None:
        """Последняя цена исхода с t ≤ T, не старше maks_vozrast_s. Итог и будущее недоступны."""
        if not (r.otkryt <= self.T < r.zakryt):
            return None
        ts, ps = r.ceny.get(r.tokeny[i_ishoda], ([], []))
        k = bisect.bisect_right(ts, self.T)
        if k == 0 or self.T - ts[k - 1] > maks_vozrast_s:
            return None
        return ps[k - 1]

    def do_zakrytiya_s(self, r: Rynok) -> int:
        """Время до ПЛАНОВОГО закрытия (endDate). Фактический closedTime стратегии не виден: рынок мог закрыться
        досрочно, и знание этого — заглядывание вперёд."""
        return r.plan - self.T


@dataclass
class Stavka:
    rynok_id: str
    i_ishoda: int
    cena: float
    T: int
    prichina: str = ""


@dataclass
class Izderzhki:
    polspreda: float = 0.01      # в долях доллара за контракт
    komissiya: float = 0.0       # доля от цены


def raschet(st: Stavka, r: Rynok, iz: Izderzhki) -> float | None:
    """Доход на 1 USD ставки после закрытия. None — итог неоднозначен (рынок отменён/50-50)."""
    if r.pobeditel is None:
        return None
    vh = min(0.999, st.cena + iz.polspreda) * (1 + iz.komissiya)
    vyplata = 1.0 if r.pobeditel == st.i_ishoda else 0.0
    return vyplata / vh - 1.0


def progon(rynki: list[Rynok], strategiya: Callable[[Proshloe], list[Stavka]], momenty: list[int], iz: Izderzhki,
           odna_na_rynok: bool = True) -> dict:
    po_id = {r.id: r for r in rynki}
    vzyato: set[str] = set(); sdelki = []
    for T in momenty:
        okno = Proshloe(rynki, T)
        for st in strategiya(okno):
            if odna_na_rynok and st.rynok_id in vzyato:
                continue
            r = po_id[st.rynok_id]
            if not (r.otkryt <= T < r.zakryt) or st.T != T:
                raise RuntimeError(f"стратегия заглянула вперёд: {st}")
            d = raschet(st, r, iz)
            if d is None:
                continue
            vzyato.add(st.rynok_id)
            sdelki.append(dict(id=r.id, kat=r.kategoriya, T=T, zakryt=r.zakryt, cena=st.cena, dohod=d,
                               vyigrysh=r.pobeditel == st.i_ishoda, prichina=st.prichina))
    x = [s["dohod"] for s in sdelki]
    n = len(x); m = sum(x) / n if n else 0.0
    sd = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1)) if n > 2 else float("nan")
    return dict(n=n, srednee=m, t=m / (sd / math.sqrt(n)) if n > 2 and sd > 0 else float("nan"),
                dolya_vyigrysha=sum(s["vyigrysh"] for s in sdelki) / n if n else 0.0, sdelki=sdelki)


def kalibrovka(rynki: list[Rynok], gorizont_s: int, korziny=(0, .05, .1, .2, .3, .4, .5, .6, .7, .8, .9, .95, 1.0001)):
    """Для каждого бинарного рынка: цена исхода 0 за gorizont_s до закрытия → частота фактического выигрыша по корзинам."""
    acc = {i: [0, 0, 0.0] for i in range(len(korziny) - 1)}
    for r in rynki:
        if r.pobeditel is None or len(r.ishody) != 2:
            continue
        p = Proshloe(rynki, r.zakryt - gorizont_s).cena(r, 0)
        if p is None:
            continue
        b = bisect.bisect_right(korziny, p) - 1
        a = acc[b]; a[0] += 1; a[1] += int(r.pobeditel == 0); a[2] += p
    return [dict(ot=korziny[i], do=korziny[i + 1], n=a[0], cena_sred=a[2] / a[0] if a[0] else None,
                 chastota=a[1] / a[0] if a[0] else None) for i, a in acc.items()]


def summa_menshe_edinicy(rynki: list[Rynok], momenty: list[int], porog: float = 0.98) -> list[dict]:
    """Группы взаимоисключающих рынков, где сумма цен YES в момент T < porog (кандидат «купить все»)."""
    out = []
    for T in momenty:
        okno = Proshloe(rynki, T); gr: dict[str, list] = {}
        for r in okno.otkrytye():
            if r.gruppa:
                gr.setdefault(r.gruppa, []).append(r)
        for g, rr in gr.items():
            if len(rr) < 2:
                continue
            ps = [okno.cena(r, 0) for r in rr]
            if any(p is None for p in ps):
                continue
            if sum(ps) < porog:
                out.append(dict(T=T, gruppa=g, n=len(rr), summa=sum(ps)))
    return out


# ---------------------------------------------------------------- примеры стратегий (НЕ подобраны, для стенда)
def favorit_za_sutki(okno: Proshloe, nizh: float = 0.80, verh: float = 0.95) -> list[Stavka]:
    """Покупка фаворита (цена исхода в [nizh, verh)) за ≤ 24 ч до планового закрытия."""
    out = []
    for r in okno.otkrytye():
        if okno.do_zakrytiya_s(r) > 24 * 3600:
            continue
        for i in range(len(r.ishody)):
            p = okno.cena(r, i)
            if p is not None and nizh <= p < verh:
                out.append(Stavka(r.id, i, p, okno.T, "favorit_24h")); break
    return out
