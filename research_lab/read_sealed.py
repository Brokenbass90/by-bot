#!/usr/bin/env python3
"""read_sealed.py — чтение запечатанного периода. ОДИН РАЗ И НАВСЕГДА.

Период 2025-10-01 … 2026-08-11, 137 символов, 265 суток. Ни разу
не читан. Это третье независимое окно, и оно больше второго.

ПЕЧАТЬ ТРАТИТСЯ ОДИН РАЗ. После запуска этот период перестаёт быть
независимым навсегда: любой последующий подбор под него — самообман.

Скрипт НЕ ЗАПУСТИТСЯ без флага --i-understand-this-spends-the-seal
и без файла-разрешения research_lab/prereg/SEAL_APPROVAL.txt,
который владелец создаёт руками.

ЧИТАЮТСЯ ТОЛЬКО ДВЕ ЗАМОРОЖЕННЫЕ КОНФИГУРАЦИИ. Никакого перебора
осей, никаких вариантов, никакого выбора лучшего.

    ATT1  шорт, стоп ×6, удержание 336 ч, BTC в [-2%, 0) от EMA200
    SBR1  лонг, стоп ×4, удержание 168 ч, BTC в [0, +2%) от EMA200

Правила заморожены в предрегистрациях, написанных ДО того, как
кто-либо посмотрел на эти данные:
    PREREG_FLAT_DOWN_2026_08_18.md
    PREREG_FLAT_UP_2026_08_19.md

КРИТЕРИИ, ОБЪЯВЛЕННЫЕ ДО ОТКРЫТИЯ:

  Нога считается ПОДТВЕРЖДЁННОЙ, если одновременно:
    эдж над случайным входом > 0;
    значимость эджа σ > 2.0;
    сделок >= 200.

  Нога считается ОПРОВЕРГНУТОЙ, если эдж <= 0 при n >= 200.

  При n < 200 вердикт «не хватило данных», нога остаётся кандидатом.

  Портфель считается подтверждённым, если подтверждена хотя бы одна
  нога И помесячный итог портфеля положителен.

Результат записывается независимо от знака. Отрицательный результат
такой же итог, как положительный.
"""
from __future__ import annotations
import argparse, glob, importlib, json, math, os, sys, datetime as dt
from pathlib import Path
import numpy as np

ROOT = str(Path(__file__).resolve().parents[1])
DATA = f"{ROOT}/research_lab/data/h1"
APPROVAL = Path(f"{ROOT}/research_lab/prereg/SEAL_APPROVAL.txt")
RECEIPT = Path(f"{ROOT}/research_lab/prereg/SEAL_SPENT.json")
sys.path.insert(0, ROOT); sys.path.insert(0, f"{ROOT}/research_lab")
from research_machine import Store, ema, simulate
from random_control import sim_geo

SEAL_FROM = 1759276800000          # 2025-10-01
FLAT, DRAWS = 0.02, 20
LEGS = [("alt_trendline_touch_v1", "AltTrendlineTouchV1Strategy", "ATT1",
         "short", 6.0, 336, "флет-", "8"),
        ("sloped_break_retest_v1", "SlopedBreakRetestV1Strategy", "SBR1",
         "long", 4.0, 168, "флет+", "0")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--i-understand-this-spends-the-seal", action="store_true")
    a = ap.parse_args()
    if not a.i_understand_this_spends_the_seal:
        print("Отказ: нужен флаг --i-understand-this-spends-the-seal"); return 2
    if not APPROVAL.exists():
        print(f"Отказ: нет файла разрешения {APPROVAL}")
        print("Владелец должен создать его руками. Это последний барьер.")
        return 2
    if RECEIPT.exists():
        print(f"Отказ: печать уже потрачена, см. {RECEIPT}"); return 2

    files = sorted(glob.glob(f"{DATA}/*.npz"))
    d = np.load(f"{DATA}/BTCUSDT.npz")
    c = d["ohlcv"][:, 3].astype(float); em = ema(c, 200)
    bts, bdist = d["ts"], (c - em) / em

    def reg(t, want):
        j = max(0, int(np.searchsorted(bts, t, side="right")) - 1)
        v = float(bdist[j]) if j < len(bdist) else 0.0
        return (-FLAT <= v < 0) if want == "флет-" else (0 <= v < FLAT)

    out = {}
    for mod, cls, pfx, side, mult, hold, rg, cd in LEGS:
        for k in list(os.environ):
            if k.startswith(pfx + "_"):
                del os.environ[k]
        os.environ.update({f"{pfx}_SYMBOL_ALLOWLIST": ",".join(Path(f).stem for f in files),
                           f"{pfx}_ALLOW_LONGS": "1", f"{pfx}_ALLOW_SHORTS": "1"})
        if cd != "0":
            os.environ[f"{pfx}_COOLDOWN_BARS_5M"] = cd
        for m in list(sys.modules):
            if m.startswith("strategies."):
                del sys.modules[m]
        S = getattr(importlib.import_module(f"strategies.{mod}"), cls)
        real, ctrl = [], [[] for _ in range(DRAWS)]
        rng = np.random.default_rng(17)
        for fp in files:
            dd = np.load(fp); ts, o = dd["ts"], dd["ohlcv"].astype(float)
            if len(ts) < 500:
                continue
            bars = [[int(ts[x]), o[x, 0], o[x, 1], o[x, 2], o[x, 3], o[x, 4]]
                    for x in range(len(ts))]
            st = Store(Path(fp).stem); strat = S(); block = -1
            start = int(np.searchsorted(ts, SEAL_FROM))
            for i in range(max(120, start - 200), len(bars) - 1):
                st.rows = bars[: i + 1]; b = bars[i]
                try:
                    s = strat.maybe_signal(st, b[0], b[1], b[2], b[3], b[4], b[5])
                except Exception:
                    continue
                if s is None or s.side != side or i <= block:
                    continue
                if b[0] < SEAL_FROM or not reg(b[0], rg):
                    continue
                r = simulate(bars, i, side, s.sl, list(s.tps or []),
                             (s.tp_fracs or [0.55])[0], mult, hold)
                if r is None:
                    continue
                block = i + r["bars"] + 1
                real.append(dict(R=r["R"], ts=int(b[0]), sym=Path(fp).stem))
                pool = np.flatnonzero((ts >= SEAL_FROM) & (np.arange(len(ts)) < len(ts) - 1))
                if len(pool) < 5:
                    continue
                sp = 1.0 / r["lev"]
                for dr in range(DRAWS):
                    x = sim_geo(bars, int(rng.choice(pool)), side == "short",
                                sp, 1.2, 2.5, 0.55, hold)
                    if x is not None:
                        ctrl[dr].append(x)
        R = np.array([x["R"] for x in real])
        cm = np.array([np.mean(x) for x in ctrl if len(x) > 20])
        if len(R) < 20 or len(cm) < 5:
            out[pfx] = dict(n=len(R), verdict="не хватило данных")
            print(f"{pfx}: сделок {len(R)} — не хватило данных"); continue
        edge = float(R.mean() - cm.mean())
        se = math.sqrt(R.std(ddof=1) ** 2 / len(R) + cm.var(ddof=1))
        z = edge / se if se else 0.0
        v = ("ПОДТВЕРЖДЕНА" if (edge > 0 and z > 2.0 and len(R) >= 200)
             else "ОПРОВЕРГНУТА" if (edge <= 0 and len(R) >= 200)
             else "не хватило данных")
        out[pfx] = dict(n=len(R), mean=float(R.mean()), ctrl=float(cm.mean()),
                        edge=edge, sigma=z, winrate=float((R > 0).mean()),
                        total=float(R.sum()), verdict=v)
        print(f"\n{pfx}: сделок {len(R)}, итог {R.sum():+.1f}R, на сделку {R.mean():+.4f}R, "
              f"винрейт {(R>0).mean():.0%}")
        print(f"  случайный вход {cm.mean():+.4f}R -> ЭДЖ {edge:+.4f}R при {z:+.2f}σ")
        print(f"  ВЕРДИКТ: {v}")
    RECEIPT.write_text(json.dumps(
        dict(spent_at_utc=dt.datetime.utcnow().isoformat(), result=out),
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nпечать потрачена, расписка: {RECEIPT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
