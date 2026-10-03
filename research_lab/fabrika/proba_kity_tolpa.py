#!/usr/bin/env python3
"""proba_kity_tolpa.py — дешёвый экран ОСУЩЕСТВИМОСТИ кандидата KITY_PROTIV_TOLPY (Binance: топ-трейдеры vs все аккаунты).
Только признаки, БЕЗ доходностей: исходы не смотрим, окна не тратим.

Вопросы (ответ — PASS / FAIL / BLOCKED по каждому):
  Q1 в архиве metrics есть count_toptrader_long_short_ratio и sum_toptrader_long_short_ratio, заполнены ≥ 90% точек
     (2021-12, 2023-06, 2025-06, 2026-09);
  Q2 расхождение несёт новую информацию: поперечная ранговая корреляция «топ-трейдеры» vs «все аккаунты»
     по ~60 монетам на 00:00 UTC < 0.8 (иначе это та же TOLPA);
  Q3 сигнал доступен вживую: публичный /futures/data/topLongShortAccountRatio отвечает (история API ~30 дней —
     поэтому вперёд копить нужно самим, а прошлое — только архив).
Запускать на Mac (сеть VM к Binance закрыта):
    python3 research_lab/fabrika/proba_kity_tolpa.py
"""
import json, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dannye_binance as B

DATY = ["2021-12-01", "2023-06-01", "2025-06-01", "2026-09-01"]


def stroki(s, d):
    b = B.get(B.url_m(s, d))
    return B.csv_iz_zip(b) if b else None


def rang(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); r = [0] * len(v)
    for k, i in enumerate(o):
        r[i] = k
    return r


def spearman(a, b):
    ra, rb = rang(a), rang(b); n = len(a); ma = sum(ra) / n; mb = sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra) ** .5; vb = sum((y - mb) ** 2 for y in rb) ** .5
    return cov / (va * vb) if va and vb else float("nan")


def main():
    print("Q1 колонки и заполненность (BTCUSDT):")
    q1 = True
    for d in DATY:
        r = stroki("BTCUSDT", d)
        if not r:
            print(f"  {d}: файла нет"); q1 = False; continue
        h = r[0]; print(f"  {d}: {h}")
        for col in ("count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio", "count_long_short_ratio"):
            if col not in h:
                print(f"    нет колонки {col}"); q1 = False; continue
            i = h.index(col); ok = sum(1 for x in r[1:] if B.fl(x[i]) is not None) / max(1, len(r) - 1)
            print(f"    {col}: заполнено {ok:.0%}"); q1 &= ok >= 0.9
    print("Q1:", "PASS" if q1 else "FAIL")

    print("Q2 ранговая корреляция топ-трейдеров и толпы по монетам, 00:00 UTC:")
    q2 = []
    papki, _ = B.listing("data/futures/um/daily/metrics/")
    sim = sorted({p.rstrip('/').split('/')[-1] for p in papki if p.rstrip('/').endswith('USDT') and '_' not in p})
    for d in ("2023-06-01", "2025-06-01"):
        a, b = [], []
        for s in sim:
            if len(a) >= 60:
                break
            r = stroki(s, d)
            if not r or "count_toptrader_long_short_ratio" not in r[0]:
                continue
            h = r[0]; x = r[1]
            t, c = B.fl(x[h.index("count_toptrader_long_short_ratio")]), B.fl(x[h.index("count_long_short_ratio")])
            if t is not None and c is not None:
                a.append(t); b.append(c)
        rho = spearman(a, b) if len(a) >= 20 else float("nan")
        print(f"  {d}: монет {len(a)}, rho = {rho:.2f}"); q2.append(rho)
    print("Q2:", "PASS" if q2 and all(x < 0.8 for x in q2) else ("FAIL" if q2 and all(x == x for x in q2) else "BLOCKED"))

    print("Q3 живой API:")
    try:
        u = "https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol=BTCUSDT&period=1d&limit=2"
        x = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "research"}), timeout=30).read())
        print("  ", x[-1]); print("Q3: PASS")
    except Exception as e:
        print("  ", type(e).__name__, str(e)[:120]); print("Q3: BLOCKED")


if __name__ == "__main__":
    main()
