#!/usr/bin/env python3
"""kalibrovka_mozga.py — паспорт чувствительности «мозга» (классификатора исходов) ДО любых реальных данных. 14.10.2026.

Вопрос: если у стратегии (например ATT1) есть контекстный сигнал «когда сделка лучше», с какой силой его вообще
можно увидеть на выборке её размера — и как часто тест обманется на шуме или на нестабильном по эпохам сигнале?

Замороженный тест (тот же, что предлагается для ATT1 KONTEKST, см. ATT1_KLADBISCHE_RAZBOR_2026_10_13.md):
  • три эпохи; leave-one-era-out: учим на двух, меряем AUC на третьей;
  • эпоха проходит, если AUC ≥ 0.55 И выше 95-го перцентиля AUC при перемешанных метках (перестановки внутри обучения);
  • PASS только если прошли ВСЕ три эпохи.
Модель — логистическая регрессия на numpy (консервативная база; LightGBM позже, тест тот же).

Случаи (синтетика, 8 контекстных признаков ~N(0,1)):
  SHUM — признаки не связаны с исходом;  STABIL_<auc> — один стабильный линейный сигнал заданной истинной AUC;
  NESTABIL — сигнал меняет знак по эпохам (как у ATT1_FILTER: «формы разные в 2023/2024/2025»).
    python3 research_lab/factory_v3/kalibrovka_mozga.py [--n 1376] [--povtorov 40]
"""
import argparse, json, sys, time
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data" / "factory_v3" / "KALIBROVKA_MOZGA.json"
K, PORG_AUC, PERESTANOVOK = 8, 0.55, 40
BETY = {"STABIL_0.55": 0.18, "STABIL_0.60": 0.36, "STABIL_0.65": 0.55, "STABIL_0.70": 0.75}   # β → истинная AUC (проверяется ниже)


def auc(y, s):
    o = np.argsort(s, kind="mergesort"); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    p = y.sum(); n = len(y) - p
    return 0.5 if p == 0 or n == 0 else (r[y == 1].sum() - p * (p + 1) / 2) / (p * n)


def logreg(X, y, l2=1.0, it=25):
    X1 = np.c_[np.ones(len(X)), X]; w = np.zeros(X1.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X1 @ w)); g = X1.T @ (p - y) + l2 * np.r_[0, w[1:]]
        H = (X1 * (p * (1 - p))[:, None]).T @ X1 + l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        w -= np.linalg.solve(H, g)
    return w


def predskazat(w, X): return np.c_[np.ones(len(X)), X] @ w


def sintetika(sluchay, n, rng):
    X = rng.standard_normal((n, K)); era = np.repeat(np.arange(3), -(-n // 3))[:n]
    if sluchay == "SHUM": z = np.zeros(n)
    elif sluchay == "NESTABIL": z = 0.55 * X[:, 0] * np.array([1, -1, 1])[era]
    else: z = BETY[sluchay] * X[:, 0]
    y = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(float)
    return X, y, era


def test(X, y, era, rng):
    """Замороженный критерий: все три эпохи (вне обучения) AUC ≥ 0.55 и выше 95% перестановок."""
    eph = []
    for e in range(3):
        tr, te = era != e, era == e
        a = auc(y[te], predskazat(logreg(X[tr], y[tr]), X[te]))
        nul = [auc(y[te], predskazat(logreg(X[tr], rng.permutation(y[tr])), X[te])) for _ in range(PERESTANOVOK)]
        eph.append(dict(auc=round(float(a), 4), p95=round(float(np.quantile(nul, 0.95)), 4), ok=bool(a >= PORG_AUC and a > np.quantile(nul, 0.95))))
    return all(x["ok"] for x in eph), eph


def istinnaya_auc(sluchay, rng, n=200_000):
    X, y, era = sintetika(sluchay, n, rng)
    if sluchay == "NESTABIL": return round(float(np.mean([auc(y[era == e], X[era == e, 0] * [1, -1, 1][e]) for e in range(3)])), 3)
    return round(float(auc(y, X[:, 0])), 3)


def main(n=1376, povtorov=40, pisat=True, seed=20261014):
    rng = np.random.default_rng(seed); t0 = time.time(); rez = {}
    for s in ["SHUM", "NESTABIL", *BETY]:
        prohod = sum(test(*sintetika(s, n, rng), rng)[0] for _ in range(povtorov))
        rez[s] = dict(istinnaya_auc=istinnaya_auc(s, rng), dolya_pass=round(prohod / povtorov, 3))
    out = dict(n=n, povtorov=povtorov, priznakov=K, kriteriy=f"все 3 эпохи: AUC ≥ {PORG_AUC} и > p95 из {PERESTANOVOK} перестановок",
               model="логистическая регрессия (numpy)", seed=seed, sluchai=rez, sekund=round(time.time() - t0, 1))
    if pisat: OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=1376); ap.add_argument("--povtorov", type=int, default=40)
    a = ap.parse_args(); print(json.dumps(main(a.n, a.povtorov), ensure_ascii=False, indent=1))
