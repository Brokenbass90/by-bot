#!/usr/bin/env python3
"""ПРОБА ЖИВОСТИ: почему стратегия не даёт сигналов.

    python3 research_lab/strategy_liveness_probe.py sloped_break_retest_v1
    python3 research_lab/strategy_liveness_probe.py sloped_break_retest_v1 SOLUSDT 30000

Отвечает на вопрос «может быть, она написана неправильно» — не мнением,
а трассировкой: на какой строке стратегия выходит и сколько раз.

ЗАЧЕМ. Аудит 6785 прогонов показал четыре стратегии, которые не дали
ни одной сделки НИ РАЗУ: `sloped_resistance_choch_v1` (187 прогонов),
`alt_inplay_breakdown_v2` (50), `sloped_break_retest_v1` (42),
`alt_support_reclaim_v1` (17). Это не «стратегия не работает» —
это стратегия, которая не может сработать. Причину никто не искал.

ЧТО ДЕЛАЕТ
  1. Строит KlineStore из data_cache и прогоняет стратегию по барам.
  2. Считает сигналы.
  3. Если сигналов нет — трассирует, на каких строках происходит выход,
     и печатает топ с исходным кодом этих строк.
  4. Отдельно показывает строки, которые НЕ выполнились ни разу,
     внутри функции сигнала: недостижимый код — самая частая причина.

ЧЕМ ЭТО ЛУЧШЕ ПОДБОРА ПАРАМЕТРОВ
  Свип порогов по сломанной стратегии даёт нули при любых параметрах
  и выглядит как «стратегия плохая». Проверено на `sloped_break_retest_v1`:
  ослабление каждого из восьми порогов по очереди и всех сразу —
  ноль сигналов во всех девяти вариантах. Причина была не в порогах.

  Найдено этой пробой: `expire_ts = tf_ts + окно * self._tf_seconds`,
  где `tf_ts` в МИЛЛИСЕКУНДАХ, а `_tf_seconds` в СЕКУНДАХ. Заявка на
  ретест жила 28.8 секунды вместо 8 часов и умирала до первой же
  проверки. Одна `* 1000` -> 0 сигналов стало 9 на 104 днях SOL.

  Стратегия в живом пути, поэтому файл НЕ ПРАВЛЕН — правку делает Codex.
"""
from __future__ import annotations

import collections
import glob
import importlib
import json
import linecache
import sys
from pathlib import Path

sys.path.insert(0, ".")


def load_candles(symbol: str, limit: int):
    from backtest.engine import Candle
    best, n = None, 0
    for p in glob.glob(f"data_cache/{symbol}_5_*.json"):
        try:
            rows = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            continue
        if len(rows) > n:
            best, n = rows, len(rows)
    if not best:
        return []
    out = []
    for x in best[:limit]:
        if isinstance(x, dict):
            out.append(Candle(ts=int(float(x["ts"])), o=float(x["o"]), h=float(x["h"]),
                              l=float(x["l"]), c=float(x["c"]), v=float(x.get("v", 0) or 0)))
        else:
            out.append(Candle(ts=int(float(x[0])), o=float(x[1]), h=float(x[2]),
                              l=float(x[3]), c=float(x[4]),
                              v=float(x[5]) if len(x) > 5 else 0.0))
    return out


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "sloped_break_retest_v1"
    symbol = sys.argv[2] if len(sys.argv) > 2 else "SOLUSDT"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 30000

    from backtest.engine import KlineStore
    mod = importlib.import_module(f"strategies.{name}")
    classes = [getattr(mod, n) for n in dir(mod)
               if n.endswith("Strategy") or n.endswith("V1") or n.endswith("V2")]
    classes = [c for c in classes if isinstance(c, type)
               and any(hasattr(c, m) for m in ("maybe_signal", "evaluate"))]
    if not classes:
        print(f"в {name} не найден класс стратегии с maybe_signal/evaluate")
        return 1
    cls = classes[0]
    entry = "maybe_signal" if hasattr(cls, "maybe_signal") else "evaluate"

    cs = load_candles(symbol, limit)
    if len(cs) < 2000:
        print(f"мало данных по {symbol}")
        return 1
    days = len(cs) * 5 / 1440
    print(f"{name}.{entry}   {symbol}   {len(cs)} баров ({days:.0f} дней)\n")

    store = KlineStore(symbol, cs, base_interval_min=5)
    s = cls()
    fn = mod.__file__

    executed = collections.Counter()
    returns = collections.Counter()
    last = {"l": 0}

    def tracer(frame, event, arg):
        if frame.f_code.co_filename != fn:
            return None
        if event == "line":
            executed[frame.f_lineno] += 1
            last["l"] = frame.f_lineno
        elif event == "return" and arg is None:
            returns[last["l"]] += 1
        return tracer

    n_sig = 0
    n_exc = collections.Counter()
    sys.settrace(tracer)
    for i in range(len(cs)):
        store.i5 = i; store.i = i; store.i_base = i
        try:
            if entry == "maybe_signal":
                r = s.maybe_signal(store, cs[i].ts, cs[i].o, cs[i].h, cs[i].l, cs[i].c, cs[i].v)
            else:
                r = s.evaluate(store, i)
            if r is not None:
                n_sig += 1
        except Exception as e:
            n_exc[type(e).__name__] += 1
    sys.settrace(None)

    print(f"СИГНАЛОВ: {n_sig}")
    if n_exc:
        print(f"исключений: {dict(n_exc)}")
    if n_sig > 0:
        print("\nСтратегия живая. Дальше её можно свипать параметрами.")
        return 0

    print("\nНОЛЬ СИГНАЛОВ — ищем, где выходит\n")
    print("частые точки выхода:")
    for line, cnt in returns.most_common(8):
        print(f"  строка {line:>4}  x{cnt:<7} {linecache.getline(fn, line).strip()[:84]}")

    # недостижимый код внутри тела функции сигнала
    src = Path(fn).read_text(encoding="utf-8").splitlines()
    start = next((i + 1 for i, l in enumerate(src) if f"def {entry}(" in l), None)
    if start:
        end = len(src)
        for i in range(start, len(src)):
            l = src[i]
            if l.strip() and not l.startswith((" ", "\t")):
                end = i; break
        dead = [i + 1 for i in range(start, end)
                if src[i].strip() and not src[i].strip().startswith("#")
                and executed[i + 1] == 0]
        if dead:
            print(f"\nНЕДОСТИЖИМЫЙ КОД в {entry} ({len(dead)} строк) — обычно здесь и причина:")
            for line in dead[:12]:
                print(f"  строка {line:>4}   {linecache.getline(fn, line).strip()[:80]}")
            if len(dead) > 12:
                print(f"  ... ещё {len(dead) - 12}")
        else:
            print("\nНедостижимого кода нет — причина в порогах или в данных.")

    print("\nДальше: смотри, какая ветка перед недостижимым блоком всегда "
          "выбирает противоположный путь. Ноль сигналов при ослаблении ВСЕХ "
          "порогов означает структурную ошибку, а не настройку.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
