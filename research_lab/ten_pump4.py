#!/usr/bin/env python3
"""ten_pump4.py — ТЕНЬ PUMP4. Собирает решения ВПЕРЁД, без денег.

Конфигурация заморожена в
research_lab/prereg/PREREG_PUMP4_PLATO_2026_08_31.md и здесь не меняется.

    стратегия  pump_fade_v4r : PumpFadeV4RStrategy
    стоп       x4 от сигнала
    удержание  168 баров (7 суток)
    цели       собственные, 0.9R и 1.8R, доля первой 0.55
    вселенная  40 символов с самой длинной историей

ПОЧЕМУ ТЕНЬ, А НЕ ЕЩЁ ОДИН ПРОГОН ПО ИСТОРИИ
============================================
Клетка x4/168 выбрана ПО ИСТОРИИ. Значит история для неё больше
не доказательство — на ней уже настраивались. Единственное честное
доказательство — решения, принятые ВПЕРЁД, после сегодняшнего дня.

Порог: 50 закрытых решений. Раньше вердикта нет.

Ордеров не ставит. Ключей не читает. Только публичные свечи Bybit.

    python3 research_lab/ten_pump4.py            # один проход
    python3 research_lab/ten_pump4.py --otchet   # что накопилось
"""
from __future__ import annotations
import argparse, atexit, glob, importlib, json, os, sys, time, urllib.request
from pathlib import Path
import numpy as np

KOREN = Path(__file__).resolve().parents[1]
os.chdir(KOREN); sys.path.insert(0, str(KOREN)); sys.path.insert(0, str(KOREN/"research_lab"))
from research_machine import zapisat_sboy, Store, simulate, pervyy_argument            # noqa: E402
from random_control import sim_geo                      # noqa: E402

ZHURNAL = Path("research_lab/data/ten_pump4.jsonl")
SOST = Path("research_lab/data/ten_pump4_sostoyanie.json")
ZAMOK = Path("research_lab/data/ten_pump4.lock")

MODUL, KLASS, PFX = "pump_fade_v4r", "PumpFadeV4RStrategy", "PUMP4"
STOP_MULT, HOLD, F1, MAX_LEV = 4.0, 168, 0.55, 100.0
PROG = 50
DRAWS = 10
NACHALO_TENI = None   # ставится при первом запуске и больше не меняется


def zanyat_zamok() -> bool:
    """Не дать двум теням работать одновременно.

    1 сентября запустились две копии сразу: обе пишут в один журнал и в
    один файл состояния. Это дубли решений и потерянный список виденных
    сигналов — то есть выдуманные числа. Дешевле запретить.
    """
    if ZAMOK.exists():
        try:
            chuzhoy = int(ZAMOK.read_text().strip())
            os.kill(chuzhoy, 0)          # жив?
        except (ValueError, ProcessLookupError, OSError):
            pass                          # мёртвый замок, забираем
        else:
            print(f"ТЕНЬ УЖЕ РАБОТАЕТ, процесс {chuzhoy}. Второй копии не будет.")
            print(f"  остановить:  kill {chuzhoy}")
            return False
    ZAMOK.parent.mkdir(parents=True, exist_ok=True)
    ZAMOK.write_text(str(os.getpid()))
    atexit.register(lambda: ZAMOK.unlink(missing_ok=True))
    return True


def svechi(sym: str, limit: int = 1000) -> list | None:
    u = (f"https://api.bybit.com/v5/market/kline?category=linear"
         f"&symbol={sym}&interval=60&limit={limit}")
    try:
        r = urllib.request.Request(u, headers={"User-Agent": "ten/1.0"})
        with urllib.request.urlopen(r, timeout=25) as f:
            d = json.loads(f.read().decode())
        lst = ((d.get("result") or {}).get("list") or [])
        out = []
        for x in reversed(lst):          # Bybit отдаёт от новых к старым
            out.append([int(x[0]), float(x[1]), float(x[2]),
                        float(x[3]), float(x[4]), float(x[5])])
        return out or None
    except Exception:
        return None


def vselennaya(skolko: int = 0) -> list[str]:
    """Монеты для тени. skolko=0 — ВСЕ доступные.

    Почему расширяем (1 сентября). Ось мерилась на 40 самых глубоких
    монетах и дала 11 сделок в месяц. 50 решений при такой частоте —
    139 дней, почти пять месяцев ожидания вердикта.
    Доступно 137 монет, и все они торгуются СЕЙЧАС: для прогноза вперёд
    глубина истории не нужна, нужен живой рынок. 137 монет дают примерно
    38 сделок в месяц -> вердикт за шесть недель вместо пяти месяцев.
    Основание, что расширять можно: analiz_vselennoy.py не нашёл ни
    одного признака монеты, который делит прибыльные и убыточные
    (возраст и волатильность отпали после починки медианного деления).
    Раз делителя нет, нет и причины считать остальные 97 монет другими.
    Если он найдётся позже — это условие пересмотра, а не оправдание.
    """
    g = []
    for fp in sorted(glob.glob("research_lab/data/h1/*.npz")):
        ts = np.load(fp)["ts"]
        if len(ts): g.append((int(ts[0]), Path(fp).stem))
    g.sort()
    return [s for _, s in (g[:skolko] if skolko else g)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--otchet", action="store_true")
    ap.add_argument("--simvolov", type=int, default=0,
                    help="сколько монет; 0 = все доступные")
    ap.add_argument("--minut", type=int, default=0, help="крутиться столько минут")
    ap.add_argument("--pauza", type=int, default=3600, help="секунд между проходами")
    a = ap.parse_args()

    zapisi = []
    if ZHURNAL.exists():
        for s in ZHURNAL.open(encoding="utf-8"):
            try: zapisi.append(json.loads(s))
            except ValueError: pass

    if a.otchet:
        zakr = [z for z in zapisi if z.get("R") is not None]
        print("=" * 64)
        print(f"ТЕНЬ PUMP4   решений закрыто: {len(zakr)} из {PROG}")
        print("=" * 64)
        if not zakr:
            print("  пока пусто. Тень собирает решения вперёд, это недели.")
            return 0
        R = np.array([z["R"] for z in zakr], float)
        cm = np.array([z["ctrl"] for z in zakr if z.get("ctrl") is not None], float)
        po = {}
        for z in zakr: po.setdefault(z["sym"], []).append(z["R"])
        plus = sum(1 for v in po.values() if np.mean(v) > 0)
        print(f"  средний R          {R.mean():+.4f}")
        print(f"  итог               {R.sum():+.2f}R")
        print(f"  винрейт            {(R>0).mean():.0%}")
        print(f"  монет в плюсе      {plus}/{len(po)}")
        if len(cm) > 10:
            ed = float(R.mean() - cm.mean())
            print(f"  случайный вход     {cm.mean():+.4f}   ЭДЖ {ed:+.4f}R")
        print()
        if len(zakr) < PROG:
            print(f"  ВЕРДИКТА НЕТ: нужно {PROG} решений, есть {len(zakr)}.")
        else:
            print("  Порог набран. Критерии — в предрегистрации.")
        return 0

    # ── проход сбора ────────────────────────────────────────────────
    sost = json.loads(SOST.read_text(encoding="utf-8")) if SOST.exists() else {}
    if "nachalo" not in sost:
        sost["nachalo"] = int(time.time() * 1000)
        print(f"ТЕНЬ ЗАПУЩЕНА. Решения принимаются только с этого момента.")
    nachalo = sost["nachalo"]
    vidennye = set(sost.get("vidennye", []))

    syms = vselennaya(a.simvolov)
    os.environ.update({f"{PFX}_SYMBOL_ALLOWLIST": ",".join(syms),
                       f"{PFX}_ALLOW_LONGS": "1", f"{PFX}_ALLOW_SHORTS": "1"})
    K = getattr(importlib.import_module(f"strategies.{MODUL}"), KLASS)

    novyh, zakryto, netu = 0, 0, 0
    rng = np.random.default_rng(int(time.time()) % 100000)
    f = ZHURNAL.open("a", encoding="utf-8")
    for sym in syms:
        b = svechi(sym)
        if not b or len(b) < 300:
            netu += 1
            continue
        strat = K(); st = Store(sym)
        pervyy = sym if pervyy_argument(K) == "symbol" else st
        for i in range(200, len(b) - 1):
            st.rows = b[: i + 1]; r_ = b[i]
            if r_[0] < nachalo:            # решения ДО старта тени не в счёт
                continue
            klyuch = f"{sym}:{r_[0]}"
            if klyuch in vidennye:
                continue
            try: s = strat.maybe_signal(pervyy, r_[0], r_[1], r_[2], r_[3], r_[4], r_[5])
            except Exception as _e:
                zapisat_sboy('ten_pump4', _e)
                continue
            if s is None or getattr(s, "side", None) not in ("long", "short"):
                continue
            vidennye.add(klyuch)
            novyh += 1
            res = simulate(b, i, s.side, s.sl, list(s.tps or []),
                           (s.tp_fracs or [F1])[0], STOP_MULT, HOLD)
            zap = {"ts": r_[0], "sym": sym, "side": s.side,
                   "zapisano": int(time.time()*1000)}
            if res is not None and res.get("lev", 0) <= MAX_LEV:
                # сделка успела закрыться внутри доступной истории
                zap["R"] = round(res["R"], 4)
                # Цели контроля считаются от РАСШИРЕННОГО стопа —
                # от того же риска, которым simulate меряет R.
                # До 1 сентября здесь стоял родной стоп, и контроль
                # получал цели в STOP_MULT раз дальше сделки.
                e = b[i+1][1]
                sl_w = e + (s.sl - e) * STOP_MULT
                risk = abs(e - sl_w)
                rr = [abs(q-e)/risk for q in (s.tps or [])] if risk > 0 else []
                k1 = rr[0] if rr else 999.0
                k2 = rr[1] if len(rr) > 1 else 999.0
                pool = [j for j in range(200, len(b)-1)]
                c = [sim_geo(b, int(rng.choice(pool)), s.side == "short",
                             1.0/res["lev"], k1, k2, (s.tp_fracs or [F1])[0], HOLD)
                     for _ in range(DRAWS)]
                c = [x for x in c if x is not None]
                zap["ctrl"] = round(float(np.mean(c)), 4) if c else None
                zakryto += 1
            f.write(json.dumps(zap, ensure_ascii=False) + "\n")
    f.close()
    sost["vidennye"] = sorted(vidennye)[-20000:]
    SOST.write_text(json.dumps(sost, ensure_ascii=False), encoding="utf-8")

    vsego_zakr = len([z for z in zapisi if z.get("R") is not None]) + zakryto
    print(f"проход завершён: новых сигналов {novyh}, из них закрылось {zakryto}")
    if netu: print(f"  символов без данных: {netu}")
    print(f"  ВСЕГО ЗАКРЫТЫХ РЕШЕНИЙ: {vsego_zakr} из {PROG}")
    print(f"  отчёт:  python3 research_lab/ten_pump4.py --otchet")
    return 0


if __name__ == "__main__":
    # Режим ДОЛГОГО ПРОЦЕССА вместо cron.
    # cron на macOS не имеет доступа к ~/Documents (TCC): каждый запуск падал
    # с "Operation not permitted" и тень 12 часов не собирала ничего.
    # Терминал владельца доступ имеет, поэтому крутимся одним процессом.
    _ap = argparse.ArgumentParser(add_help=False)
    _ap.add_argument("--minut", type=int, default=0)
    _ap.add_argument("--pauza", type=int, default=3600)
    _a, _ = _ap.parse_known_args()
    if "--otchet" not in sys.argv and not zanyat_zamok():
        raise SystemExit(1)
    if _a.minut <= 0:
        raise SystemExit(main())
    _konets = time.time() + _a.minut * 60
    _n = 0
    while time.time() < _konets:
        _n += 1
        print(f"\n--- проход {_n}   {time.strftime('%Y-%m-%d %H:%M:%S')} ---", flush=True)
        try:
            main()
        except Exception as _e:
            print(f"  проход упал: {type(_e).__name__}: {_e}", flush=True)
        if time.time() >= _konets:
            break
        time.sleep(max(60, _a.pauza))
    print("\nтень отработала заданное время", flush=True)
    raise SystemExit(0)
