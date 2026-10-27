#!/usr/bin/env python3
"""ten.py — ОБЩАЯ тень вперёд. Одна гипотеза, один журнал, один вердикт.

ЧЕМ ОТЛИЧАЕТСЯ ОТ ten_pump4.py
==============================
Тот написан под одну стратегию и под рыночный вход. Этот берёт любую
стратегию, умеет ЛИМИТНЫЙ вход по той же модели, что лаборатория, и
считает ДВА контроля — обычный и по режиму. Иначе тень мерила бы не то,
на чём гипотеза дошла до предрегистрации.

ten_pump4.py трогать не надо: он крутится с PUMP4 и у него свой замок.

ГЛАВНОЕ ПРАВИЛО
===============
Решение засчитывается, только если бар пришёл ПОСЛЕ первого запуска.
Момент старта пишется в состояние один раз и больше не меняется.
Всё, что было до — история, а история на эту гипотезу уже потрачена.

ЗАПУСК (долгим процессом, не через cron: cron на macOS не имеет
доступа к ~/Documents и тень молча стоит):

    python3 research_lab/ten.py elder_triple_screen_v2 \
        ElderTripleScreenV2Strategy ETS2 \
        --otstup 0.002 --zhdat 6 --stop 4 --hold 336 \
        --minut 100000 --pauza 3600

    python3 research_lab/ten.py ... --otchet
"""
from __future__ import annotations
import argparse
import atexit
import importlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

KOREN = Path(__file__).resolve().parents[1]
os.chdir(KOREN)
sys.path.insert(0, str(KOREN))
sys.path.insert(0, str(KOREN / "research_lab"))

import numpy as np                                                  # noqa: E402
from research_machine import (Store, MAX_LEV, pervyy_dlya,          # noqa: E402
                              zapisat_sboy, otchet_sboev)
from random_control import sim_limit, sim_geo                       # noqa: E402
from research_machine import simulate, ema                          # noqa: E402
from osi import rezhim_ryad, metka_rezhima                          # noqa: E402

DATA = Path("research_lab/data")
ROZYGRYSHEY = 20
# Насколько поздно мы увидели закрывшийся бар, чтобы решение всё ещё
# годилось для проверки ИСПОЛНЕНИЯ. Бар часовой, один час на проход,
# час запаса. Всё, что позже, — это наверстывание после сна или
# перезапуска: для альфы годится, для исполнения НЕТ.
VOVREMYA_CHASOV = 2
SLOTOV_SCHYOTA = 3      # лимит ПОРТФЕЛЯ, замороженное решение владельца

# ВАРИАНТЫ ВЫХОДА. Включаются флагом --varianty и пишутся В ОТДЕЛЬНЫЕ
# журналы рядом с основным. Вход, стоп, отступ, ожидание, сторона, режим
# и вселенная НЕ меняются ни на йоту — меняется только выход. Значит три
# ветки видят один и тот же сигнал по построению, а не по совпадению.
#
# Цифры объявлены в research_lab/PREREG_TRI_TENI_2026_09_15.md ДО пуска и
# после пуска не трогаются. Подбора не будет: WIDE берёт 0.5R не потому,
# что 0.5 лучше на прошлом, а потому что это ровно вдвое меньше
# несимметричности, чем 0.25R против стопа 1R.
VAR_24H_HOLD = 24                    # ветка ETS2S_24H: закрыть через сутки
VAR_WIDE_RR1, VAR_WIDE_RR2 = 0.5, 1.0   # ветка ETS2S_WIDE: широкая цель


def svechi(sym: str, limit: int = 1000) -> list | None:
    u = (f"https://api.bybit.com/v5/market/kline?category=linear"
         f"&symbol={sym}&interval=60&limit={limit}")
    try:
        r = urllib.request.Request(u, headers={"User-Agent": "ten/2.0"})
        with urllib.request.urlopen(r, timeout=25) as f:
            d = json.loads(f.read().decode())
        lst = ((d.get("result") or {}).get("list") or [])
        return [[int(x[0]), float(x[1]), float(x[2]),
                 float(x[3]), float(x[4]), float(x[5])] for x in reversed(lst)] or None
    except Exception:
        return None


def vselennaya(skolko: int = 0) -> list[str]:
    u = "https://api.bybit.com/v5/market/tickers?category=linear"
    try:
        r = urllib.request.Request(u, headers={"User-Agent": "ten/2.0"})
        with urllib.request.urlopen(r, timeout=25) as f:
            lst = json.loads(f.read().decode())["result"]["list"]
    except Exception as e:
        print(f"  вселенная не получена: {type(e).__name__}")
        return []
    par = [(x["symbol"], float(x.get("turnover24h") or 0)) for x in lst
           if x["symbol"].endswith("USDT")]
    par.sort(key=lambda z: -z[1])
    syms = [p[0] for p in par]
    return syms[:skolko] if skolko else syms


def prefiks_strategii(modul: str) -> str | None:
    """НАСТОЯЩИЙ префикс переменных стратегии, а не выдуманный нами.

    ДЕФЕКТ, найден 3 сентября, второй раз за три дня. Тень ETS2S ставила
    ETS2S_SYMBOL_ALLOWLIST, а elder_triple_screen_v2 читает
    ETS2_SYMBOL_ALLOWLIST. Переменные уходили в пустоту, и тень могла
    молча простоять месяц с нулём сигналов.

    Первый раз это случилось 1 сентября с PUMP4 и было записано в ITOG.
    Значит проверка обязана стоять В КОДЕ, а не в моей памяти.
    """
    import re as _re
    f = KOREN / "strategies" / f"{modul}.py"
    if not f.exists():
        return None
    nayd = _re.findall(r"([A-Z][A-Z0-9_]*)_SYMBOL_ALLOWLIST",
                       f.read_text(errors="ignore"))
    return max(set(nayd), key=nayd.count) if nayd else None


def zanyat_zamok(zamok: Path) -> bool:
    if zamok.exists():
        try:
            chuzhoy = int(zamok.read_text().strip())
            os.kill(chuzhoy, 0)
        except (ValueError, ProcessLookupError, OSError):
            pass
        else:
            print(f"ЭТА ТЕНЬ УЖЕ РАБОТАЕТ, процесс {chuzhoy}. Второй копии не будет.")
            print(f"  остановить:  kill {chuzhoy}")
            return False
    zamok.parent.mkdir(parents=True, exist_ok=True)
    zamok.write_text(str(os.getpid()))
    atexit.register(lambda: zamok.unlink(missing_ok=True))
    return True


def otchet(a, zhurnal: Path) -> int:
    zapisi = []
    if zhurnal.exists():
        for s in zhurnal.open(encoding="utf-8"):
            try:
                zapisi.append(json.loads(s))
            except ValueError:
                pass
    zakr = [z for z in zapisi if z.get("R") is not None]
    zhdut = [z for z in zapisi if z.get("R") is None and z.get("zhdyot")]
    print("=" * 66)
    print(f"ТЕНЬ {a.prefiks}   решений ЗАКРЫТО ПОЛНОСТЬЮ: {len(zakr)} из {a.porog}")
    print(f"  ждут своего срока: {len(zhdut)} "
          f"(сделка считается только когда прошли все {a.hold} ч)")
    print("=" * 66)
    if not zakr:
        print("  пока пусто. Тень собирает решения ВПЕРЁД, это недели.")
        return 0
    # 27.10: журнал с наложениями (одна монета — новое решение при открытой позиции) вердикта не даёт.
    try:
        sys.path.insert(0, str(KOREN / "research_lab" / "fabrika"))
        from audit_nalozheniy import dolya_nalozheniy, bez_nalozheniy
        _dn = dolya_nalozheniy(zakr)
    except Exception:
        _dn, bez_nalozheniy = 0.0, None
    if _dn > 0.05:
        print(f"  НАЛОЖЕНИЯ: {_dn:.0%} решений — повторный вход в открытую позицию той же монеты.")
        print("  ВЕРДИКТ ПО ЭТОМУ ЖУРНАЛУ ЗАБЛОКИРОВАН. Ниже — только решения без наложений (описательно).")
        zakr = bez_nalozheniy(zakr, a.zhdat)
        a.porog = 10 ** 9                       # вердикт не выносится
    R = np.array([z["R"] for z in zakr], float)
    cm = np.array([z["ctrl"] for z in zakr if z.get("ctrl") is not None], float)
    cr = np.array([z["ctrl_rezhim"] for z in zakr
                   if z.get("ctrl_rezhim") is not None], float)
    po = {}
    for z in zakr:
        po.setdefault(z["sym"], []).append(z["R"])
    print(f"  средний R            {R.mean():+.4f}")
    print(f"  итог                 {R.sum():+.2f}R")
    print(f"  винрейт              {(R > 0).mean():.0%}")
    print(f"  монет в плюсе        {sum(1 for v in po.values() if np.mean(v) > 0)}/{len(po)}")
    predl = len(zapisi)
    print(f"  доля исполнения      {len(zakr)/predl:.0%} ({len(zakr)} из {predl} предложено)")
    print()

    def edzh(c, imya):
        if len(c) < 30:
            print(f"  {imya:<22} контроль не собрался ({len(c)})")
            return None
        e = float(R.mean() - c.mean())
        se = float(np.sqrt(R.std(ddof=1) ** 2 / len(R) + c.var(ddof=1)))
        if not (se > 1e-12):
            print(f"  {imya:<22} нулевой разброс — считать нельзя")
            return None
        print(f"  {imya:<22} {e:+.4f}R   σ {e/se:+.2f}")
        return e / se

    edzh(cm, "эдж сырой")
    z_r = edzh(cr, "ЭДЖ ПО РЕЖИМУ")
    print()
    print("  Решение принимается ТОЛЬКО по эджу по режиму. Сырой печатается,")
    print("  чтобы было видно, сколько в результате обычной экспозиции.")
    print()
    if len(zakr) < a.porog:
        print(f"  ВЕРДИКТА НЕТ: нужно {a.porog} решений, есть {len(zakr)}.")
        if z_r is not None and len(zakr) >= a.porog // 3 and z_r < 0:
            print("  ВНИМАНИЕ: режимный эдж отрицателен на трети пути.")
            print("  Условие досрочной остановки — в предрегистрации.")
    elif z_r is None:
        print("  ПОРОГ НАБРАН, но контроль не собрался. Вердикта нет.")
    elif z_r > 2.87:
        print(f"  ПОРОГ НАБРАН И ПРОЙДЕН: σ {z_r:+.2f} > 2.87.")
        print("  Дальше — печать, потом канарейка на минимальных деньгах.")
    else:
        print(f"  ПОРОГ НАБРАН, НЕ ПРОЙДЕН: σ {z_r:+.2f} <= 2.87.")
        print("  Гипотеза отклоняется. Клетку НЕ двигать: сдвинули — новая")
        print("  гипотеза, новая тень.")
    return 0


def prohod(a, K, zhurnal: Path, sost: dict) -> tuple:
    nachalo = sost["nachalo"]
    vidennye = set(sost.get("vidennye", []))
    syms = vselennaya(a.simvolov)
    if not syms:
        return 0, 0, 0
    nastoyashchiy = prefiks_strategii(a.modul)
    pfx_env = a.env or nastoyashchiy or a.prefiks
    if nastoyashchiy and not a.env and nastoyashchiy != a.prefiks:
        print(f"  ПРЕФИКС ПЕРЕМЕННЫХ: стратегия читает {nastoyashchiy}_*, "
              f"имя тени {a.prefiks}. Ставлю {nastoyashchiy}_*.", flush=True)
    os.environ.update({f"{pfx_env}_SYMBOL_ALLOWLIST": ",".join(syms),
                       f"{pfx_env}_ALLOW_LONGS": "1",
                       f"{pfx_env}_ALLOW_SHORTS": "1"})
    if a.kuldaun:
        os.environ[f"{pfx_env}_COOLDOWN_BARS_5M"] = str(a.kuldaun)
    # РЕЖИМ BTC. Считается по свежим барам BTC, только по прошлому.
    btc_ok = None
    if a.rezhim:
        bb = svechi("BTCUSDT")
        if bb:
            cb = np.array([x[4] for x in bb], dtype=float)
            eb = ema(cb, 200)
            otkl = (cb - eb) / np.where(np.abs(eb) < 1e-12, 1e-12, eb)
            btc_ok = {int(bb[i][0]): (
                (-0.02 <= otkl[i] < 0) if a.rezhim == "флет-" else (0 <= otkl[i] < 0.02))
                for i in range(len(bb))}
    rng = np.random.default_rng(int(time.time()) % 100000)
    novyh = zakryto = netu = 0
    ozhidaet = []
    snimki = []
    varianty = {}
    dozrelo = 0
    zhdut_ranshe = {(x["sym"], x["ts"]) for x in sost.get("ozhidaet", [])}
    # 27.10 (--blok-zhurnal): занятость монеты по журналу этой тени и ждущим решениям — сквозь проходы.
    # Дефект без флага: блок жил только внутри прохода, а виденные сигналы пропускались, не ставя блок →
    # у ETS2S 78 % решений наложены на ещё открытую позицию той же монеты (ETS2S_POVTOR_ITOG_2026_10_27.md).
    zanyato = {}
    if getattr(a, "blok_zhurnal", False):
        BESK = 10 ** 15
        if zhurnal.exists():
            for _s in zhurnal.open(encoding="utf-8"):
                try: _z = json.loads(_s)
                except Exception: continue
                if "R" in _z and _z.get("barov") is not None:
                    zanyato.setdefault(_z["sym"], []).append((int(_z["ts"]), int(_z["ts"]) + (int(_z["barov"]) + a.zhdat + 2) * 3600000))
        for _w in sost.get("ozhidaet", []):
            zanyato.setdefault(_w["sym"], []).append((int(_w["ts"]), BESK))
    _okno = (a.hold + a.zhdat + 2) * 3600000
    def _zanyata(_sym, _t):
        # занята, если внутри уже принятой позиции ИЛИ если уже есть решение в пределах удержания ПОСЛЕ _t
        # (сдвиг окна 1000 баров может «найти» сигнал задним числом раньше уже принятого)
        return any(a0 < _t < b0 or _t < a0 < _t + _okno for a0, b0 in zanyato.get(_sym, ()))
    f = zhurnal.open("a", encoding="utf-8")
    for sym in syms:
        b = svechi(sym)
        if not b or len(b) < 300:
            netu += 1
            continue
        strat = K()
        st = Store(sym)
        pervyy = pervyy_dlya(K, st, sym)
        metki = np.array([metka_rezhima(x) for x in rezhim_ryad(b)])
        # БЛОКИРОВКА. Дефект найден 3 сентября на первых сутках тени.
        # В лаборатории после входа следующие сигналы по этой монете
        # пропускаются до выхода — иначе одна монета даёт несколько
        # наложенных позиций. В тени этого не было: наблюдения выходили
        # перекрытыми и связанными, а связанные наблюдения завышают
        # значимость, потому что их считают независимыми.
        block = -1
        for i in range(200, len(b) - 1):
            if i <= block:
                continue
            st.rows = b[: i + 1]
            r_ = b[i]
            if r_[0] < nachalo:
                continue
            klyuch = f"{sym}:{r_[0]}"
            # ждущее решение НЕ пропускаем: оно могло дозреть
            if klyuch in vidennye and (sym, int(r_[0])) not in zhdut_ranshe:
                continue
            try:
                s = strat.maybe_signal(pervyy, r_[0], r_[1], r_[2], r_[3], r_[4], r_[5])
            except Exception as _e:
                zapisat_sboy("ten", _e)
                continue
            if s is None or getattr(s, "side", None) not in ("long", "short"):
                continue
            if a.storona != "любая" and s.side != a.storona:
                continue
            if btc_ok is not None:
                bl = max([x for x in btc_ok if x <= r_[0]], default=None)
                if bl is None or not btc_ok[bl]:
                    continue
            bylo_zhdushchim = (sym, int(r_[0])) in zhdut_ranshe
            if zanyato is not None and not bylo_zhdushchim and _zanyata(sym, int(r_[0])):
                vidennye.add(klyuch)          # монета занята открытой позицией этой тени — сигнал не решение
                continue
            if not bylo_zhdushchim:
                novyh += 1
            vidennye.add(klyuch)
            short = s.side == "short"
            e_ref = float(b[i + 1][1])
            sl_w = e_ref + (float(s.sl) - e_ref) * a.stop
            risk_w = abs(e_ref - sl_w)
            if risk_w <= 0 or e_ref <= 0:
                continue
            sp = risk_w / e_ref
            if 1.0 / sp > MAX_LEV:
                continue
            tl = list(s.tps or [])
            k1 = abs(tl[0] - e_ref) / risk_w if len(tl) > 0 else 999.0
            k2 = abs(tl[1] - e_ref) / risk_w if len(tl) > 1 else 999.0
            f1 = float((s.tp_fracs or [0.55])[0])
            teper = int(time.time() * 1000)
            zapozdanie = (teper - int(r_[0])) / 3600000.0
            # ДВА ЖУРНАЛА В ОДНОМ. Замечание третьего рецензента, и оно
            # верное. Пропущенный из-за сна ноутбука сигнал МОЖНО честно
            # досчитать для альфы: бары никуда не делись. Но нельзя
            # делать вид, что заявка стояла на бирже, пока машина спала.
            #   vovremya=True  — годится и для альфы, и для ИСПОЛНЕНИЯ
            #   vovremya=False — только для альфы, наверстано задним числом
            zap = {"ts": r_[0], "sym": sym, "side": s.side,
                   "zapisano": teper,
                   "zapozdanie_ch": round(zapozdanie, 2),
                   "vovremya": bool(zapozdanie <= VOVREMYA_CHASOV)}
            # 17.10: ГЕОМЕТРИЯ РЕШЕНИЯ — в ПЕРВОЙ записи (запрос Codex для причинного адаптера хеджа).
            # Всё ниже посчитано выше из баров ≤ i+1 ДО записи; ни на какое решение не влияет.
            # Исполняемое правило (ELDER_CRASH_HEDGE_V1_1): stop_dolya от e_ref, стоп/цели — от ФАКТИЧЕСКОГО
            # исполнения (yadro.prodvinut): risk = fill·stop_dolya, sl = fill ± risk, tp_k = fill ∓ rr_k·risk.
            zap["geom"] = {"v": 1, "ref_close": float(b[i][4]), "e_ref": e_ref, "raw_sl": float(s.sl),
                           "raw_tps": [float(x) for x in tl], "stop_x": float(a.stop), "sl_w": sl_w,
                           "stop_dolya": round(sp, 6), "rr1": round(k1, 3), "rr2": round(k2, 3), "f1": f1,
                           "max_lev": MAX_LEV, "bar_ts_signal": int(r_[0]), "bar_ts_eref": int(b[i + 1][0])}
            # НАБЛЮДЕНИЕ, не фильтр. Номер касания линии и число прошлых
            # пробоев пишутся рядом с исходом и НИ НА ЧТО не влияют: ни
            # одно решение из-за них не отбрасывается. Предрегистрация
            # research_lab/prereg/PREREG_ATT1_KASANIE_2026_09_14.md.
            # Обёрнуто в try намеренно: тень набирает единственное наше
            # свидетельство вперёд и не имеет права упасть из-за того,
            # что мы захотели посчитать рядом ещё одно число.
            try:
                from att1_kasanie import kasanie_i_proboi as _kip
                _k, _p = _kip(b, i, str(getattr(s, "reason", "") or ""), s.side)
                if _k is not None:
                    zap["kasanie"] = _k
                    zap["probitiy"] = _p
            except Exception:
                pass
            # ДЕФЕКТ, найден 3 сентября. sim_limit, не дождавшись стопа
            # или цели, закрывает сделку по ПОСЛЕДНЕМУ ДОСТУПНОМУ бару.
            # В тени возрастом в сутки это значит, что КАЖДАЯ сделка
            # закрывалась через сутки вместо своих 336 часов. Отсюда
            # винрейт 20% против 70% на печати: сделкам не давали дойти.
            # Теперь решение засчитывается, только если окно удержания
            # ПОЛНОСТЬЮ уместилось в имеющиеся бары. Остальные ждут.
            zaderzhka = a.zhdat if a.vhod == "limit" else 0
            # СОЗРЕВАНИЕ. Первая версия требовала, чтобы уместилось всё окно
            # в 336 часов, и первые числа появлялись только через 14 суток.
            # Но медиана удержания ETS2S — 87 часов: 72% сделок доходят до
            # стопа или цели за неделю. Такая сделка ЗАКРЫТА, ждать нечего.
            # Ждём только те, которые упёрлись в край данных и были бы
            # закрыты по времени, а не по стопу и не по цели.
            dostupno = len(b) - 1 - (i + zaderzhka)
            hvatilo = dostupno > 1
            if not hvatilo:
                res = None
            elif a.vhod == "limit":
                res = sim_limit(b, i, short, sp, k1, k2, f1, a.hold,
                                a.otstup, a.zhdat, a.fee_vhod, a.fee_vyhod)
            else:
                # РЫНОЧНЫЙ ВХОД следующим баром — контракт ATT1
                rr = simulate(b, i, s.side, s.sl, list(s.tps or []), f1,
                              a.stop, a.hold)
                res = ((rr["R"], rr["bars"], True)
                       if rr is not None and rr.get("lev", 0) <= MAX_LEV else None)
            # обрезана краем данных, а не стопом и не целью — значит ждёт
            if res is not None and res[1] >= min(dostupno, a.hold) and dostupno < a.hold:
                res = None
            if res is None and hvatilo:
                # ПОЗИЦИЯ ОТКРЫТА ПРЯМО СЕЙЧАС. Пишем причинный снимок:
                # только то, что известно на этот час. Снимки нужны, чтобы
                # позже проверить гипотезу «управляющий умеет закрывать
                # сломавшуюся идею раньше срока». Восстановить их задним
                # числом нельзя, поэтому копим с первого дня, ЗАДОЛГО до
                # того, как появится сам управляющий.
                vh = i + zaderzhka
                if vh < len(b) - 1:
                    cena_vh = float(b[vh][4]); tek = float(b[-1][4])
                    hod = (cena_vh - tek) / cena_vh if short else (tek - cena_vh) / cena_vh
                    okno = [float(x[4]) for x in b[vh:]]
                    luchshe = ((cena_vh - min(okno)) / cena_vh if short
                               else (max(okno) - cena_vh) / cena_vh)
                    huzhe = ((max(okno) - cena_vh) / cena_vh if short
                             else (cena_vh - min(okno)) / cena_vh)
                    snimki.append({
                        "chas": int(b[-1][0]), "sym": sym, "side": s.side,
                        "ts_signala": int(r_[0]),
                        "chasov_v_sdelke": len(b) - 1 - vh,
                        "tekushchiy_R": round(hod / sp, 3),
                        "luchshiy_R": round(luchshe / sp, 3),
                        "hudshiy_R": round(huzhe / sp, 3),
                        "do_stopa_R": round(1.0 - huzhe / sp, 3),
                        "do_tseli_R": round(k1 - hod / sp, 3),
                        "rezhim": str(metki[-1]),
                        "plecho": round(1.0 / sp, 2),
                    })
            if res is None:
                zap["zhdyot"] = True
                ozhidaet.append({"sym": sym, "ts": int(r_[0])})
            if res is not None:
                block = i + zaderzhka + res[1] + 1
                # РАЗБИВКА ЗАТРАТ. Без неё нельзя сверить лабораторный PnL
                # с реальным на канарейке: видно только итог, а не из чего
                # он сложился. Восстановить задним числом невозможно —
                # поэтому пишется с первой же сделки.
                lev = 1.0 / sp if sp > 0 else float("nan")
                zatraty = lev * (a.fee_vhod + a.fee_vyhod) / 1e4
                zap["R"] = round(res[0], 4)
                zap["R_valovo"] = round(res[0] + zatraty, 4)
                zap["zatraty_R"] = round(zatraty, 4)
                zap["plecho"] = round(lev, 2)
                zap["stop_dolya"] = round(sp, 6)
                zap["barov"] = int(res[1])
                zap["rr1"] = round(k1, 3)
                zap["rr2"] = round(k2, 3)
                pool = np.arange(200, len(b) - 2)

                def _kontrol(j_):
                    """Контроль ТЕМ ЖЕ типом входа, что и сделка.

                    Сравнивать лимитный вход стратегии с рыночным входом
                    случайного — это измерять разницу типов ордера, а не
                    качество момента. Ошибка того же класса, что цели
                    контроля в чужих единицах.
                    """
                    if a.vhod == "limit":
                        x = sim_limit(b, j_, short, sp, k1, k2, f1, a.hold,
                                      a.otstup, a.zhdat, a.fee_vhod, a.fee_vyhod)
                        return None if x is None else x[0]
                    return sim_geo(b, j_, short, sp, k1, k2, f1, a.hold)

                c = [_kontrol(int(rng.choice(pool))) for _ in range(ROZYGRYSHEY)]
                c = [x for x in c if x is not None]
                zap["ctrl"] = round(float(np.mean(c)), 4) if c else None
                pool_r = pool[metki[pool] == metki[i]]
                if len(pool_r) >= 5:
                    cr = [_kontrol(int(rng.choice(pool_r))) for _ in range(ROZYGRYSHEY)]
                    cr = [x for x in cr if x is not None]
                    zap["ctrl_rezhim"] = round(float(np.mean(cr)), 4) if cr else None
                # ТРИ ВЫХОДА НА ОДНОМ СИГНАЛЕ. Считается только тогда,
                # когда закрылась КОНТРОЛЬНАЯ сделка, поэтому три журнала
                # покрывают ровно один и тот же набор решений. Иначе ветки
                # набирали бы разные выборки и сравнивать их было бы нельзя.
                # Контроли случайного входа в варианты НЕ копируются: они
                # считались под контрольную геометрию и для другой цели
                # были бы враньём.
                if getattr(a, "varianty", False):
                    for imya, rr1_, rr2_, hold_ in (
                            ("24H", k1, k2, VAR_24H_HOLD),
                            ("WIDE", VAR_WIDE_RR1, VAR_WIDE_RR2, a.hold)):
                        rv = sim_limit(b, i, short, sp, rr1_, rr2_, f1,
                                       hold_, a.otstup, a.zhdat,
                                       a.fee_vhod, a.fee_vyhod)
                        zv = {k_: v_ for k_, v_ in zap.items()
                              if k_ not in ("ctrl", "ctrl_rezhim")}
                        zv["variant"] = imya
                        zv["rr1"], zv["rr2"], zv["hold"] = rr1_, rr2_, hold_
                        if rv is None:
                            zv["R"], zv["barov"] = None, None
                        else:
                            zv["R"] = round(rv[0], 4)
                            zv["R_valovo"] = round(rv[0] + zatraty, 4)
                            zv["barov"] = int(rv[1])
                        varianty.setdefault(imya, []).append(zv)
                zakryto += 1
                if bylo_zhdushchim:
                    dozrelo += 1
            if res is not None or not bylo_zhdushchim:
                f.write(json.dumps(zap, ensure_ascii=False) + "\n")
                if getattr(a, "blok_zhurnal", False) and not bylo_zhdushchim:
                    _b = (int(res[1]) + a.zhdat + 2) * 3600000 if res is not None else 10 ** 15
                    zanyato.setdefault(sym, []).append((int(r_[0]), int(r_[0]) + _b))
    f.close()
    sost["vidennye"] = sorted(vidennye)[-40000:]
    sost["ozhidaet"] = ozhidaet[-20000:]
    if snimki:
        sn = Path(str(zhurnal).replace(".jsonl", "_snimki.jsonl"))
        with sn.open("a", encoding="utf-8") as g:
            for x in snimki:
                g.write(json.dumps(x, ensure_ascii=False) + "\n")
    for imya, spisok in varianty.items():
        pv = Path(str(zhurnal).replace(".jsonl", f"_{imya}.jsonl"))
        with pv.open("a", encoding="utf-8") as g:
            for x in spisok:
                g.write(json.dumps(x, ensure_ascii=False) + "\n")
    sost["dozrelo"] = int(sost.get("dozrelo", 0)) + dozrelo
    return novyh, zakryto, netu


def paritet(zhurnal: Path, drugoy: Path) -> int:
    """Ветка CONTROL обязана совпадать со старой тенью на ОДНОМ И ТОМ ЖЕ
    сигнале. Если не совпадает — сравнивать ветки между собой нельзя, и
    никакие выводы про выход не имеют силы.

    Отдельно важно: «общих сигналов нет» — это НЕ «паритет сошёлся».
    Это NOT_MEASURED, и возвращается другой код.
    """
    def chitat(p: Path) -> dict:
        d = {}
        if not p.exists():
            return d
        for s in p.read_text(encoding="utf-8").splitlines():
            if not s.strip():
                continue
            try:
                x = json.loads(s)
            except Exception:
                continue
            if x.get("R") is not None:
                d[(x["sym"], int(x["ts"]))] = x
        return d

    a_, b_ = chitat(zhurnal), chitat(drugoy)
    obshchie = sorted(set(a_) & set(b_))
    print("=" * 84)
    print(f"  ПАРИТЕТ: {zhurnal.name}  против  {drugoy.name}")
    print("=" * 84)
    print(f"  решений здесь {len(a_)}, там {len(b_)}, общих сигналов {len(obshchie)}")
    if not obshchie:
        print("  общих сигналов пока нет. Это NOT_MEASURED, а не «сошлось».")
        print("=" * 84)
        return 2
    # ДЕФЕКТ, пойман самопроверкой 15 сентября: журнал, сверенный САМ С
    # СОБОЙ, показывал три расхождения. Причина — `x.get("barov") or -1`:
    # ноль баров ложен как значение, и сделка, закрывшаяся в тот же бар,
    # превращалась в -1 с одной стороны и в -2 с другой. Сравнение с
    # нулём нельзя писать через `or`. Отсюда правило: сверка паритета
    # обязана прогоняться на самом себе ДО того, как ей верят.
    def _bar(x):
        v = x.get("barov")
        return None if v is None else int(v)

    plohie = [k for k in obshchie
              if abs(float(a_[k]["R"]) - float(b_[k]["R"])) > 1e-9
              or _bar(a_[k]) != _bar(b_[k])]
    for k in plohie[:10]:
        print(f"    {k[0]} {k[1]}: R {a_[k]['R']} против {b_[k]['R']}, "
              f"баров {a_[k].get('barov')} против {b_[k].get('barov')}")
    if plohie:
        print(f"  РАСХОЖДЕНИЙ {len(plohie)} из {len(obshchie)}. Паритета НЕТ.")
        print("  Пока он не сошёлся, сравнение веток между собой недействительно.")
    else:
        print(f"  СОВПАЛО ВСЁ: {len(obshchie)} общих сигналов, R и число баров")
        print("  одинаковы до последнего знака. Ветки сравнимы.")
    print("=" * 84)
    return 1 if plohie else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("modul")
    ap.add_argument("klass")
    ap.add_argument("prefiks")
    ap.add_argument("--env", default=None, help="префикс переменных стратегии, если другой")
    ap.add_argument("--otstup", type=float, required=False, default=0.002)
    ap.add_argument("--zhdat", type=int, default=6)
    ap.add_argument("--stop", type=float, default=4.0)
    ap.add_argument("--hold", type=int, default=336)
    ap.add_argument("--fee-vhod", type=float, default=1.5)
    ap.add_argument("--fee-vyhod", type=float, default=5.5)
    ap.add_argument("--vhod", choices=["limit", "rynok"], default="limit",
                    help="ЗАМОРОЖЕННЫЙ тип входа. ETS2S — лимит, ATT1 — рынок.")
    ap.add_argument("--rezhim", default=None,
                    help="фильтр режима BTC: «флет-» или «флет+». ATT1 по своей "
                         "предрегистрации торгует только во флете вниз.")
    ap.add_argument("--kuldaun", type=int, default=0,
                    help="ЗАМОРОЖЕННЫЙ кулдаун стратегии в барах 5м (ATT1 = 8)")
    ap.add_argument("--storona", choices=["long", "short", "любая"], default="любая",
                    help="ЗАМОРОЖЕННАЯ сторона. ETS2S по предрегистрации "
                         "торгует ТОЛЬКО ШОРТ, и тень обязана делать то же.")
    ap.add_argument("--blok-zhurnal", dest="blok_zhurnal", action="store_true",
                    help="27.10: одна позиция на монету СКВОЗЬ проходы — новое решение по монете не принимается, пока "
                         "предыдущее (из журнала или ждущее) не вышло. Без флага — прежнее поведение (замороженные тени).")
    ap.add_argument("--porog", type=int, default=1300)
    ap.add_argument("--simvolov", type=int, default=0, help="0 = все монеты")
    ap.add_argument("--minut", type=int, default=0)
    ap.add_argument("--pauza", type=int, default=3600)
    ap.add_argument("--otchet", action="store_true")
    ap.add_argument("--varianty", action="store_true",
                    help="писать рядом два альтернативных ВЫХОДА, 24H и WIDE. "
                         "Вход, стоп, сторона и вселенная не меняются.")
    ap.add_argument("--paritet", default=None,
                    help="имя другого журнала в research_lab/data для сверки "
                         "совпадения на общих сигналах")
    a = ap.parse_args()

    zhurnal = DATA / f"ten_{a.prefiks}.jsonl"
    sostf = DATA / f"ten_{a.prefiks}_sost.json"
    DATA.mkdir(parents=True, exist_ok=True)

    if a.paritet:
        return paritet(zhurnal, DATA / a.paritet)

    if a.otchet:
        return otchet(a, zhurnal)

    if not zanyat_zamok(DATA / f"ten_{a.prefiks}.pid"):
        return 1

    sost = json.loads(sostf.read_text(encoding="utf-8")) if sostf.exists() else {}
    if "nachalo" not in sost:
        sost["nachalo"] = int(time.time() * 1000)
        sost["zamorozheno"] = {"otstup": a.otstup, "zhdat": a.zhdat,
                               "stop": a.stop, "hold": a.hold,
                               "storona": a.storona, "porog": a.porog}
        print("ТЕНЬ ЗАПУЩЕНА. Решения принимаются только с этого момента.")
        print(f"  заморожено: отступ {a.otstup}, ждать {a.zhdat}, "
              f"стоп x{a.stop}, держать {a.hold}, порог {a.porog}")
    else:
        z = sost.get("zamorozheno", {})
        raznica = {k: (v, getattr(a, k)) for k, v in z.items()
                   if k != "porog" and getattr(a, k, v) != v}
        if raznica:
            print("  ПАРАМЕТРЫ НЕ СОВПАДАЮТ С ЗАМОРОЖЕННЫМИ ПРИ СТАРТЕ:")
            for k, (bylo, stalo) in raznica.items():
                print(f"    {k}: заморожено {bylo}, передано {stalo}")
            print("  Тень с новыми параметрами — ЭТО ДРУГАЯ ГИПОТЕЗА.")
            print("  Возьми другой префикс, иначе журнал смешает две разные.")
            return 2

    konets = time.time() + a.minut * 60 if a.minut else 0
    n = 0
    while True:
        n += 1
        print(f"\n--- проход {n}   {time.strftime('%Y-%m-%d %H:%M:%S')} ---", flush=True)
        novyh, zakryto, netu = prohod(a, _klass(a), zhurnal, sost)
        otkr = len(sost.get("ozhidaet", []))
        print(f"  открытых позиций сейчас: {otkr}   "
              f"занято слотов из {SLOTOV_SCHYOTA}: {min(otkr, SLOTOV_SCHYOTA)}", flush=True)
        sostf.write_text(json.dumps(sost, ensure_ascii=False), encoding="utf-8")
        vsego = sum(1 for s in zhurnal.open(encoding="utf-8")
                    if '"R"' in s) if zhurnal.exists() else 0
        print(f"  новых сигналов {novyh}, из них исполнилось {zakryto}", flush=True)
        if netu:
            print(f"  символов без данных: {netu}", flush=True)
        print(f"  ВСЕГО ЗАКРЫТЫХ РЕШЕНИЙ: {vsego} из {a.porog}", flush=True)
        otchet_sboev()
        if not konets or time.time() >= konets:
            break
        time.sleep(a.pauza)
    print(f"\n  отчёт:  python3 research_lab/ten.py {a.modul} {a.klass} {a.prefiks} --otchet")
    return 0


def _klass(a):
    m = importlib.import_module(f"strategies.{a.modul}")
    return getattr(m, a.klass)


if __name__ == "__main__":
    raise SystemExit(main())
