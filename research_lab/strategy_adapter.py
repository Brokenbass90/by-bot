#!/usr/bin/env python3
"""
strategy_adapter.py — единый разъём к стратегиям.

ЗАЧЕМ. В strategies/ живёт минимум четыре разные конвенции вызова:

    maybe_signal(store, ts, o, h, l, c, v)        основная
    maybe_signal(store, ts, last_price)           сокращённая
    async maybe_signal(store, ts, last_price)     асинхронная
    evaluate(bars: list[dict], regime, symbol, ...)  «плоская»

Из-за этого любой инструмент аудита дотягивается примерно до трети
библиотеки, а остальные две трети падают с TypeError и выглядят как
«ноль сигналов». Так уже случалось: в августе 13 ног были записаны
в мёртвые, а оказались живыми с другим аллоулистом.

Разъём не переписывает стратегии. Он определяет конвенцию через
inspect и приводит вызов к одному виду, ЯВНО сообщая, какую конвенцию
опознал — чтобы результат можно было проверить, а не принимать на веру.

ПОЧИНЕНО ЗДЕСЬ ПО СРАВНЕНИЮ С strategy_liveness_probe.py:
  1. конвенция вызова определяется, а не предполагается;
  2. поддержана async;
  3. берутся СВЕЖИЕ бары, а не самые старые (`best[:limit]` брал начало
     2023 года — стратегии проверялись на данных трёхлетней давности);
  4. читается SYMBOL_ALLOWLIST стратегии, и проба идёт по разрешённому
     символу, а не по произвольному;
  5. класс стратегии ищется шире (не только *Strategy/*V1/*V2).
"""
from __future__ import annotations

import asyncio
import glob
import importlib
import inspect
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_lab.strategy_call_contract import first_signal_argument

CONVENTIONS = (
    "ohlcv",
    "symbol_ohlcv",
    "last_price",
    "symbol_last_price",
    "async_last_price",
    "async_symbol_last_price",
    "async_ohlcv",
    "async_symbol_ohlcv",
    "flat_bars",
    "evaluate_i",
)


# ------------------------------------------------------------------ данные
def load_candles(
    symbol: str, limit: int, tail: bool = True, end_ms: int | None = None,
    input_path: str | Path | None = None,
):
    """Свечи символа. tail=True -> САМЫЕ СВЕЖИЕ бары (важно: прежняя проба
    брала самые старые и мерила стратегии на начале 2023 года)."""
    from backtest.engine import Candle
    best, n = None, 0
    if input_path is not None:
        payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("symbol") != symbol:
            return []
        best = payload.get("records")
        n = len(best) if isinstance(best, list) else 0
    else:
        for p in glob.glob(f"data_cache/{symbol}_5_*.json"):
            try:
                rows = json.loads(Path(p).read_text(encoding="utf-8"))
            except Exception:
                continue
            if len(rows) > n:
                best, n = rows, len(rows)
    if not best:
        return []
    if end_ms is not None:
        def _ts(row):
            return int(float(row.get("ts", row.get("ts_ms")) if isinstance(row, dict) else row[0]))
        best = [row for row in best if _ts(row) <= int(end_ms)]
    chunk = best[-limit:] if tail else best[:limit]
    out = []
    for x in chunk:
        if isinstance(x, dict):
            out.append(Candle(
                ts=int(float(x.get("ts", x.get("ts_ms")))),
                o=float(x.get("o", x.get("open"))), h=float(x.get("h", x.get("high"))),
                l=float(x.get("l", x.get("low"))), c=float(x.get("c", x.get("close"))),
                v=float(x.get("v", x.get("volume", 0)) or 0),
            ))
        else:
            out.append(Candle(ts=int(float(x[0])), o=float(x[1]), h=float(x[2]),
                              l=float(x[3]), c=float(x[4]),
                              v=float(x[5]) if len(x) > 5 else 0.0))
    return out


# ------------------------------------------------------------------ класс
def find_module_entry(mod):
    """Функциональная стратегия: maybe_signal/evaluate прямо в модуле,
    без класса. Прежний детектор их просто не видел и писал НЕТ_КЛАССА."""
    for n in ("maybe_signal", "evaluate"):
        f = getattr(mod, n, None)
        if callable(f) and getattr(f, "__module__", None) == mod.__name__:
            return f
    return None


def find_strategy_class(mod):
    """Класс стратегии. Прежний поиск ловил только *Strategy/*V1/*V2
    и терял v3, v4 и всё, названное иначе."""
    cands = []
    for n in dir(mod):
        c = getattr(mod, n)
        if not isinstance(c, type):
            continue
        if getattr(c, "__module__", None) != mod.__name__:
            continue
        if any(hasattr(c, m) for m in ("maybe_signal", "evaluate")):
            cands.append(c)
    if not cands:
        return None
    # предпочитаем тот, у кого есть maybe_signal
    cands.sort(key=lambda c: (not hasattr(c, "maybe_signal"), len(c.__name__)))
    return cands[0]


def instantiate(cls):
    """Пытаемся поднять без аргументов; если не выходит — сообщаем чем."""
    try:
        return cls(), ""
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


# ------------------------------------------------------------------ конвенция
def detect_convention(obj):
    """Определяем способ вызова по сигнатуре, а не по догадке."""
    fn = getattr(obj, "maybe_signal", None)
    if fn is not None:
        sig = inspect.signature(fn)
        params = [p for p in sig.parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        n_req = sum(1 for p in params if p.default is inspect._empty)
        is_async = inspect.iscoroutinefunction(fn)
        symbol_first = first_signal_argument(obj) == "symbol"
        if n_req >= 6:
            if is_async:
                return ("async_symbol_ohlcv" if symbol_first else "async_ohlcv"), sig
            return ("symbol_ohlcv" if symbol_first else "ohlcv"), sig
        if is_async:
            return ("async_symbol_last_price" if symbol_first else "async_last_price"), sig
        return ("symbol_last_price" if symbol_first else "last_price"), sig

    fn = getattr(obj, "evaluate", None)
    if fn is not None:
        sig = inspect.signature(fn)
        names = list(sig.parameters)
        if "bars" in names:
            return "flat_bars", sig
        return "evaluate_i", sig
    return None, None


def symbol_allowlist(obj):
    """Разрешённые символы. Проба по неразрешённому символу — главная
    причина ложных «мёртвых» ног (в августе так потеряли 13 штук).

    Ищем широко: params-словарь, атрибуты объекта, атрибуты конфига.
    Ключом считаем всё, где есть ALLOWLIST / SYMBOLS / UNIVERSE."""
    def _pick(d):
        for k, v in d.items():
            ku = str(k).upper()
            if any(w in ku for w in ("ALLOWLIST", "SYMBOLS", "UNIVERSE")):
                if isinstance(v, (list, tuple, set)):
                    out = [str(x).strip() for x in v if str(x).strip()]
                elif isinstance(v, str):
                    out = [x.strip() for x in v.split(",") if x.strip()]
                else:
                    continue
                out = [x for x in out if x.endswith("USDT")]
                if out:
                    return out
        return []

    for src in (getattr(obj, "params", None), getattr(obj, "__dict__", None),
                getattr(getattr(obj, "cfg", None), "__dict__", None)):
        if isinstance(src, dict):
            got = _pick(src)
            if got:
                return got
    return []


# ------------------------------------------------------------------ вызов
def make_caller(conv, obj, symbol, regime="bull_trend"):
    """Один вызов для всех конвенций. Возвращает f(store, candles, i) -> signal|None."""
    if conv in ("ohlcv", "symbol_ohlcv"):
        return lambda st, cs, i: obj.maybe_signal(symbol if conv == "symbol_ohlcv" else st,
                                                  cs[i].ts, cs[i].o, cs[i].h,
                                                  cs[i].l, cs[i].c, cs[i].v)
    if conv in ("last_price", "symbol_last_price"):
        return lambda st, cs, i: obj.maybe_signal(
            symbol if conv == "symbol_last_price" else st,
            cs[i].ts,
            cs[i].c,
        )

    if conv in (
        "async_ohlcv",
        "async_symbol_ohlcv",
        "async_last_price",
        "async_symbol_last_price",
    ):
        loop = asyncio.new_event_loop()

        def _call(st, cs, i):
            first = symbol if "symbol" in conv else st
            if conv in ("async_ohlcv", "async_symbol_ohlcv"):
                co = obj.maybe_signal(first, cs[i].ts, cs[i].o, cs[i].h, cs[i].l, cs[i].c, cs[i].v)
            else:
                co = obj.maybe_signal(first, cs[i].ts, cs[i].c)
            return loop.run_until_complete(co)
        return _call

    if conv == "flat_bars":
        sig = inspect.signature(obj.evaluate)
        window = 300

        def _call(st, cs, i):
            lo = max(0, i - window + 1)
            bars = [dict(ts=c.ts, open=c.o, high=c.h, low=c.l, close=c.c, volume=c.v)
                    for c in cs[lo:i + 1]]
            kw = {}
            if "regime" in sig.parameters:
                kw["regime"] = regime
            if "symbol" in sig.parameters:
                kw["symbol"] = symbol
            return obj.evaluate(bars, **kw)
        return _call

    if conv == "evaluate_i":
        return lambda st, cs, i: obj.evaluate(st, i)
    return None


# ------------------------------------------------------------------ фасад
def open_strategy(
    name,
    symbol=None,
    limit=12000,
    regime="bull_trend",
    tail=True,
    end_ms: int | None = None,
    input_path: str | Path | None = None,
):
    """Открыть стратегию единообразно.

    Возвращает dict: ok, conv, symbol, candles, store, call, note.
    При ok=False поле note объясняет причину и НЕ выдаёт её за «ноль сигналов».
    """
    from backtest.engine import KlineStore
    try:
        mod = importlib.import_module(f"strategies.{name}")
    except Exception as e:
        return dict(ok=False, note=f"импорт не удался: {type(e).__name__}: {e}")

    cls = find_strategy_class(mod)
    if cls is None:
        fn = find_module_entry(mod)
        if fn is None:
            return dict(ok=False, note="класс стратегии не найден")
        obj, cls_name = mod, f"<модуль {name}>"   # функциональная стратегия
    else:
        obj, err = instantiate(cls)
        if obj is None:
            return dict(ok=False, note=f"не создаётся без аргументов: {err}", cls=cls.__name__)
        cls_name = cls.__name__

    conv, sig = detect_convention(obj)
    if conv is None:
        return dict(ok=False, note="нет ни maybe_signal, ни evaluate", cls=cls_name)

    allow = symbol_allowlist(obj)
    chosen = symbol
    note = ""
    requested = symbol
    if allow:
        if symbol is None:
            chosen = allow[0]
            note = f"символ взят из аллоулиста: {allow[:4]}"
        elif symbol not in allow:
            return dict(
                ok=False,
                conv=conv,
                symbol=symbol,
                requested_symbol=symbol,
                cls=cls_name,
                allowlist=allow,
                signature=str(sig),
                note=f"{symbol} НЕ в аллоулисте {allow[:4]} — явная проба отклонена",
            )
    chosen = chosen or "SOLUSDT"

    cs = load_candles(chosen, limit, tail=tail, end_ms=end_ms, input_path=input_path)
    if len(cs) < 500:
        return dict(ok=False, conv=conv, symbol=chosen, cls=cls_name,
                    note=f"мало данных по {chosen}: {len(cs)} баров")

    store = KlineStore(chosen, cs, base_interval_min=5)
    call = make_caller(conv, obj, chosen, regime)
    return dict(ok=True, conv=conv, symbol=chosen, requested_symbol=requested,
                cls=cls_name, obj=obj,
                candles=cs, store=store, call=call, allowlist=allow,
                signature=str(sig), note=note)


def all_strategy_names(root="strategies"):
    return sorted(Path(p).stem for p in glob.glob(f"{root}/*.py")
                  if not Path(p).stem.startswith("__"))


if __name__ == "__main__":
    n = sys.argv[1] if len(sys.argv) > 1 else "alt_momentum_breakout_v1"
    r = open_strategy(n, sys.argv[2] if len(sys.argv) > 2 else None)
    print(json.dumps({k: v for k, v in r.items()
                      if k in ("ok", "conv", "symbol", "cls", "note", "signature", "allowlist")},
                     ensure_ascii=False, indent=2))
