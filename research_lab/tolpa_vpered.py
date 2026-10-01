#!/usr/bin/env python3
"""tolpa_vpered.py — судья предрегистрации TOLPA_XS вперёд (L1 из discovery_paket7, правила один в один).
Заморожено 2026-10-01 до первых будущих данных.

Статус семьи: PROMISING / HOLDOUT_FAIL_LOW_POWER / PROSPECTIVE_REQUIRED. Порог не меняется, holdout остаётся FAIL.
Правила L1 без изменений: PIT топ-50 по OI в $, доля лонг-аккаунтов Bybit за предыдущие сутки, шорт верхнего
дециля, лонг нижнего, 7 дней, discovery_paket1.sdelka (фандинг, 12 bps на круг).
Вперёд: ребаланс каждые 7 дней, вход закрытием дней 2026-10-01 + 7k (UTC).
Вердикт — два заранее объявленных взгляда: 26 недель и 52 недели. Порог на каждом взгляде t ≥ 2.2
(поправка на два взгляда), среднее > 0, обе половины > 0. На 26 нед. PASS или ждать; на 52 нед. PASS или FAIL.
Одна семья с 1-дневной версией (пачка 8): доказательства не складываются.

Обновление данных (раз в 2–4 недели, с Mac):
  dannye_pit_kripto.py --vse --obnovit ; dannye_pit_kripto.py --lsr --obnovit ; vselennaya_usd.py
    python3 research_lab/tolpa_vpered.py
"""
import datetime as dt, json
import numpy as np
import discovery_paket1 as P

T0 = int(dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc).timestamp() * 1000); HOLD = 7; POROG = 2.2


def main():
    M = P.zagruzit_kripto()
    sostav = {d: set(v) for d, v in json.load(open(P.D / "basis/vselennaya_pit_usd50.json"))["sostav"].items()}
    for s, x in M.items():
        f = P.D / "lsr_sutochnyy" / f"{s}.json"
        m = {int(t): v for t, v in json.load(open(f))["lsr"]} if f.exists() else {}
        x["lsr"] = np.array([m.get(int(t) - P.DEN, np.nan) for t in x["ts"]])
    den = lambda t: dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).date().isoformat()
    nedeli, ozhid = [], 0
    t = T0
    while True:
        if not any(t in set(x["ts"][-40:].tolist()) for x in list(M.values())[:50]):
            break
        rows = []
        for s, x in M.items():
            i = int(np.searchsorted(x["ts"], t))
            if i >= len(x["ts"]) or x["ts"][i] != t or i < 60 or s not in sostav.get(den(t), ()):
                continue
            v = x["lsr"][i]
            if np.isfinite(v):
                rows.append((v, s, i))
        if len(rows) >= 30:
            rows.sort(); k = len(rows) // 10
            leg = [P.sdelka(M[s], i, HOLD, +1) for _, s, i in rows[:k]] + [P.sdelka(M[s], i, HOLD, -1) for _, s, i in rows[-k:]]
            leg = [r for r in leg if r is not None]
            if len(leg) == 2 * k:
                nedeli.append(float(np.mean(leg)))
            else:
                ozhid += 1
        elif den(t) not in sostav:
            print(f"нет вселенной на {den(t)} — запустить vselennaya_usd.py после обновления данных"); break
        t += 7 * P.DEN
    n = len(nedeli)
    def vzglyad(v):          # оценка на фиксированном префиксе: 26 или 52 недели, без промежуточных взглядов
        v = np.array(v); h = len(v) // 2; t_ = P.t_nw(v, 1)
        ok = v.mean() > 0 and t_ >= POROG and v[:h].mean() > 0 and v[h:].mean() > 0
        return ok, dict(srednee_bps=round(v.mean() * 1e4, 1), t=round(t_, 2),
                        polovinki_bps=(round(v[:h].mean() * 1e4, 1), round(v[h:].mean() * 1e4, 1)))
    rez = {"nedel": n, "ozhidayut_vyhoda": ozhid}
    if n >= 52:
        ok26, _ = vzglyad(nedeli[:26]); ok52, r = vzglyad(nedeli[:52]); rez.update(r)
        rez["verdikt"] = "PASS" if (ok26 or ok52) else "FAIL"
    elif n >= 26:
        ok26, r = vzglyad(nedeli[:26]); rez.update(r); rez["verdikt"] = "PASS" if ok26 else "ЖДЁМ_ДО_52"
    else:
        if n >= 3:
            rez.update(vzglyad(nedeli)[1]); rez["primechanie"] = "справка, не взгляд"
        rez["verdikt"] = "ЖДЁМ"
    print("TOLPA_XS вперёд:", json.dumps(rez, ensure_ascii=False))


if __name__ == "__main__":
    main()
