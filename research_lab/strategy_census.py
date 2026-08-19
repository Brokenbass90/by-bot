#!/usr/bin/env python3
"""
strategy_census.py — честная перепись библиотеки стратегий.

Через research_lab/strategy_adapter.py, поэтому:
  * вызывается ЛЮБАЯ конвенция, а не одна из четырёх;
  * проба идёт по РАЗРЕШЁННОМУ символу (аллоулист читается из стратегии);
  * берутся СВЕЖИЕ бары, а не начало 2023 года.

Каждая строка переписи говорит одно из:
  ЖИВАЯ N        стреляет, N сигналов — можно мерить
  НОЛЬ           вызывается корректно, но сигналов нет — вот это диагноз
  ПАДАЕТ         исключение на каждом баре — код сломан
  НЕ_ПОДНЯЛАСЬ   не создаётся без аргументов
  НЕТ_КЛАССА     не найден класс со стратегией
  НЕТ_ДАННЫХ     нет истории по разрешённому символу

Разница между НОЛЬ и остальными принципиальна: свипать параметры
осмысленно только у ЖИВАЯ; у НОЛЬ надо искать структурную причину;
у остальных — чинить код, а не логику.

Запускать повторно до конца: готовые пропускаются.
    python3 research_lab/strategy_census.py [баров] [секунд_бюджета]
"""
import json
import os
import signal
import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, "research_lab")

import strategy_adapter as A

OUT = "research_lab/results/strategy_census.json"
BARS = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
BUDGET = float(sys.argv[2]) if len(sys.argv) > 2 else 32.0

PER = float(sys.argv[3]) if len(sys.argv) > 3 else 12.0   # лимит НА ОДНУ стратегию


class _Slow(Exception):
    pass


def _alarm(sig, frm):
    raise _Slow()


signal.signal(signal.SIGALRM, _alarm)


def _save(d):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(d, open(OUT, "w"), indent=2, ensure_ascii=False)


res = json.load(open(OUT)) if os.path.exists(OUT) else {}
names = [n for n in A.all_strategy_names() if n not in res]
print(f"осталось {len(names)} из {len(A.all_strategy_names())}", flush=True)

t0 = time.time()
for name in names:
    if time.time() - t0 > BUDGET:
        print("[бюджет] запусти ещё раз", flush=True)
        break
    row = dict(name=name)
    try:
        h = A.open_strategy(name, limit=BARS)
    except Exception as e:
        res[name] = dict(row, status="ПАДАЕТ_НА_ОТКРЫТИИ", detail=f"{type(e).__name__}: {e}"[:180])
        _save(res)
        continue

    if not h.get("ok"):
        note = h.get("note", "")
        st = ("НЕТ_ДАННЫХ" if "мало данных" in note else
              "НЕ_ПОДНЯЛАСЬ" if "не создаётся" in note else
              "НЕТ_КЛАССА" if "класс" in note or "maybe_signal" in note else "НЕ_ОТКРЫЛАСЬ")
        res[name] = dict(row, status=st, conv=h.get("conv"), detail=note[:180])
        _save(res)
        print(f"{name:<38} {st}", flush=True)
        continue

    cs, store, call = h["candles"], h["store"], h["call"]
    n_sig, n_exc, first_exc, done_bars = 0, 0, "", 0
    # лимит на КАЖДУЮ стратегию: одна медленная не должна съедать весь
    # вызов и терять уже посчитанное (так уже случилось — прогон вставал
    # на одном файле и ничего не сохранял)
    signal.setitimer(signal.ITIMER_REAL, PER)
    try:
        for i in range(len(cs)):
            store.i5 = i; store.i = i; store.i_base = i
            done_bars = i + 1
            try:
                if call(store, cs, i) is not None:
                    n_sig += 1
            except _Slow:
                raise
            except Exception as e:
                n_exc += 1
                if not first_exc:
                    first_exc = f"{type(e).__name__}: {e}"[:150]
        slow = False
    except _Slow:
        slow = True
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)

    broken = n_exc >= max(done_bars, 1) * 0.9
    st = ("МЕДЛЕННАЯ" if slow and n_sig == 0 else
          "ПАДАЕТ" if broken else ("ЖИВАЯ" if n_sig > 0 else "НОЛЬ"))
    res[name] = dict(row, status=st, signals=n_sig, exc=n_exc, conv=h["conv"],
                     symbol=h["symbol"], cls=h["cls"], bars=done_bars,
                     note=h.get("note", "")[:120], detail=first_exc)
    _save(res)   # сохраняем ПОСЛЕ КАЖДОЙ, а не в конце: иначе убитый
                 # по таймауту процесс терял весь прогон
    print(f"{name:<38} {st:<8} сиг={n_sig:<5} искл={n_exc:<6} {h['conv']:<16} {h['symbol']}", flush=True)

_save(res)
print(f"[сохранено] {len(res)} -> {OUT}", flush=True)
