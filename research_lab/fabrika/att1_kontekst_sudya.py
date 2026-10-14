#!/usr/bin/env python3
"""att1_kontekst_sudya.py — ЗАМОРОЖЕННЫЙ судья PREREG_ATT1_KONTEKST_2026_10_14 (одна попытка). Запускается ОДИН раз.
Вход: data/att1_kontekst/sdelki.jsonl (att1_kontekst_sbor.py). Выход: data/att1_kontekst/ITOG.json.
"""
import datetime as dt, hashlib, json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "factory_v3"))
from kalibrovka_mozga import auc, logreg, predskazat      # noqa: E402  (та же модель, что в паспорте мозга)

VHOD = LAB / "data" / "att1_kontekst" / "sdelki.jsonl"; ITOG = LAB / "data" / "att1_kontekst" / "ITOG.json"
PRIZNAKI = ["f_vozrast_linii", "f_probitiy", "f_entrydist", "f_r2", "f_vozrast_pivota", "f_naklon", "f_body", "f_atrpct",
            "f_trend24", "f_trend72", "f_trend168", "f_rezhim_monety", "f_btc_rezhim", "f_btc_trend72"]
EPOHI = {2023: (dt.datetime(2023, 1, 1), dt.datetime(2024, 1, 1)), 2024: (dt.datetime(2024, 1, 1), dt.datetime(2025, 1, 1)),
         2025: (dt.datetime(2025, 1, 1), dt.datetime(2025, 10, 1))}
EMBARGO_MS = 14 * 86_400_000          # исключаем из обучения сделки в ±14 дн от границ тестовой эпохи (удержание 336 ч)
PORG_AUC, PERESTANOVOK, L2, SEED = 0.55, 40, 1.0, 20261014


def ms(d): return int(d.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def main():
    if ITOG.exists(): raise SystemExit("ITOG.json уже есть — попытка одна, повтор запрещён")
    raw = VHOD.read_bytes(); r = [json.loads(l) for l in raw.decode().splitlines() if l.strip()]
    kl = {(x["sym"], x["ts"]) for x in r}
    assert len(kl) == len(r), "дубликаты (sym, ts)"
    era = np.array([next((e for e, (a, b) in EPOHI.items() if ms(a) <= x["ts"] < ms(b)), -1) for x in r])
    R = np.array([x["R"] for x in r]); C = np.array([x["ctrl"] for x in r]); ts = np.array([x["ts"] for x in r])
    nich = np.abs(R - C) < 1e-9; vne_epoh = int((era == -1).sum())
    X = np.array([[np.nan if x[f] is None else float(x[f]) for f in PRIZNAKI] for x in r])
    vzyat = (era > 0) & ~nich
    X, y, era, ts = X[vzyat], (R[vzyat] > C[vzyat]).astype(float), era[vzyat], ts[vzyat]
    rng = np.random.default_rng(SEED); epohi = {}
    for e, (a, b) in EPOHI.items():
        te = era == e
        tr = (era != e) & ((ts < ms(a) - EMBARGO_MS) | (ts >= ms(b) + EMBARGO_MS))
        med = np.nanmedian(X[tr], axis=0); Xi = np.where(np.isnan(X), med, X)
        mu, sd = Xi[tr].mean(0), Xi[tr].std(0); sd[sd == 0] = 1; Z = (Xi - mu) / sd
        a_ = float(auc(y[te], predskazat(logreg(Z[tr], y[tr], l2=L2), Z[te])))
        nul = [float(auc(y[te], predskazat(logreg(Z[tr], rng.permutation(y[tr]), l2=L2), Z[te]))) for _ in range(PERESTANOVOK)]
        p95 = float(np.quantile(nul, 0.95))
        epohi[e] = dict(n_test=int(te.sum()), n_train=int(tr.sum()), dolya_y1_test=round(float(y[te].mean()), 4),
                        auc=round(a_, 4), p95_perestanovok=round(p95, 4), ok=bool(a_ >= PORG_AUC and a_ > p95))
    verdikt = "PASS" if all(v["ok"] for v in epohi.values()) else "FAIL"
    out = dict(prereg="PREREG_ATT1_KONTEKST_2026_10_14.md", vhod_sha256=hashlib.sha256(raw).hexdigest(), sdelok_vsego=len(r),
               vne_epoh=vne_epoh,
               nichyi_isklyucheno=int(nich.sum()), priznaki=PRIZNAKI, epohi=epohi, verdikt=verdikt,
               znachenie=("в контексте есть переносимая по эпохам информация об исходе ATT1 — НЕ допуск к деньгам; дальше отдельный "
                          "замороженный тест прибыльности" if verdikt == "PASS" else
                          "контекст не даёт устойчивой информации; семья ATT1 закрывается окончательно (до новых внешних данных/механизма)"),
               kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    ITOG.write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
