"""cross_sectional_momentum — НОВЫЙ кандидат-нога (DeepSeek идея 3.6).

Аномалия (Liu & Tsyvinski 2018): прошлые победители крипты продолжают расти.
Рыночно-НЕЙТРАЛЬНАЯ, НИЗКОЧАСТОТНАЯ (ребаланс раз в неделю) → устойчива к
комиссиям (главный урок §22). Структурно ОТЛИЧНА от level-стратегий → реальный
шанс некоррелированной ноги для книги.

Логика: на каждом ребалансе ранжируем монеты по доходности за lookback дней,
лонг top-K, шорт bottom-K (равный вес, дельта-нейтрально), держим до следующего
ребаланса. R считаем как доход книги / её риск (волатильность спреда).

Аддитивно, memory-safe (по символу), кэш без финального WF/gate.

Запуск:
    PYTHONPATH=. python3 backtest/cross_sectional_momentum.py
    PYTHONPATH=. python3 backtest/cross_sectional_momentum.py --lookback 30 --hold 7 --k 3
"""
from __future__ import annotations

import datetime as dt
import gc
import sys
from typing import Dict, List

from backtest.package_efficiency_run import ResampleStore, ROOT

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "ADAUSDT", "DOTUSDT",
           "LTCUSDT", "DOGEUSDT", "XRPUSDT", "AVAXUSDT", "SUIUSDT", "ONDOUSDT"]
COST_PCT_PER_REBALANCE = 0.10  # ~ оборот обеих ног, % (taker+slip), грубо


def daily_closes(sym: str) -> Dict[str, float]:
    """{YYYY-MM-DD: close} из 5m через ресэмплинг в дневки."""
    st = ResampleStore(sym)
    if not st.has_base():
        return {}
    st.set_cursor(st.bts[-1])
    rows = st.fetch_klines(sym, "D", 100000)
    out = {dt.datetime.utcfromtimestamp(r[0] / 1000.0).strftime("%Y-%m-%d"): r[4] for r in rows}
    del st; gc.collect()
    return out


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    lookback = int(argv[argv.index("--lookback") + 1]) if "--lookback" in argv else 30
    hold = int(argv[argv.index("--hold") + 1]) if "--hold" in argv else 7
    k = int(argv[argv.index("--k") + 1]) if "--k" in argv else 3
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    print("=== CROSS-SECTIONAL MOMENTUM (long winners / short losers) ===", flush=True)
    print(f"symbols={len(SYMBOLS)} lookback={lookback}d hold={hold}d top/bottom-K={k} "
          f"cost/rebal={COST_PCT_PER_REBALANCE}%\n", flush=True)

    data = {s: daily_closes(s) for s in SYMBOLS}
    data = {s: d for s, d in data.items() if len(d) > lookback + hold + 5}
    print(f"[load] {len(data)} монет с дневками", flush=True)
    # общий отсортированный календарь дат (где есть >= k*2 монет)
    all_dates = sorted(set().union(*[set(d.keys()) for d in data.values()]))

    rets: List[float] = []   # доход книги за каждый период (в %)
    monthly: Dict[str, float] = {}
    i = lookback
    while i + hold < len(all_dates):
        d0 = all_dates[i]
        # momentum = доходность за lookback к дате d0
        scores = []
        for s, d in data.items():
            past = all_dates[i - lookback]
            if d0 in d and past in d and d[past] > 0:
                scores.append((s, d[d0] / d[past] - 1.0))
        if len(scores) >= k * 2:
            scores.sort(key=lambda x: x[1], reverse=True)
            longs = [s for s, _ in scores[:k]]
            shorts = [s for s, _ in scores[-k:]]
            dN = all_dates[i + hold]
            def fwd(s):
                d = data[s]
                return (d[dN] / d[d0] - 1.0) if (d0 in d and dN in d and d[d0] > 0) else 0.0
            long_ret = sum(fwd(s) for s in longs) / k
            short_ret = sum(fwd(s) for s in shorts) / k
            book = (long_ret - short_ret) - COST_PCT_PER_REBALANCE / 100.0
            rets.append(book * 100.0)
            monthly[d0[:7]] = monthly.get(d0[:7], 0.0) + book * 100.0
        i += hold

    n = len(rets)
    if n == 0:
        print("Нет периодов."); return 0
    import statistics
    total = sum(rets)
    mean = total / n
    sd = statistics.pstdev(rets) or 1e-9
    sharpe_per = mean / sd
    periods_per_year = 365.0 / hold
    sharpe_ann = sharpe_per * (periods_per_year ** 0.5)
    eq = 1.0; peak = 1.0; dd = 0.0
    for r in rets:
        eq *= (1 + r / 100.0); peak = max(peak, eq); dd = min(dd, (eq - peak) / peak)
    green = sum(1 for v in monthly.values() if v > 0)
    print(f"\nпериодов: {n}  сделок-ребалансов: {n}", flush=True)
    print(f"итог: {total:+.1f}%  средн/период: {mean:+.2f}%  ", flush=True)
    print(f"Sharpe(annual): {sharpe_ann:.2f}  maxDD: {dd*100:.1f}%  "
          f"зелёных мес: {green}/{len(monthly)} ({100*green/len(monthly):.0f}%)", flush=True)
    verdict = "ПЕРСПЕКТИВНО" if (sharpe_ann > 1.0 and total > 0) else (
        "СЛАБО, но не мусор" if total > 0 else "НЕТ ЭДЖА на этих данных")
    print(f"ВЕРДИКТ: {verdict}", flush=True)
    out = ROOT / "runtime" / "cross_sectional_momentum_latest.json"
    try:
        import json
        out.write_text(json.dumps({"lookback": lookback, "hold": hold, "k": k,
                                   "total_pct": round(total, 1), "sharpe_ann": round(sharpe_ann, 2),
                                   "maxdd_pct": round(dd * 100, 1), "monthly": monthly}, indent=2),
                       encoding="utf-8")
        print(f"JSON -> {out}", flush=True)
    except Exception:
        pass
    print("Кэш ~год, грубые издержки. Доказательство — сервер: больше монет, "
          "длиннее история, реальные комиссии, WF по параметрам (lookback/hold/k).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
