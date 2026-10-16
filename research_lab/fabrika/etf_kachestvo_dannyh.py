#!/usr/bin/env python3
"""etf_kachestvo_dannyh.py — вердикт качества причинного ряда ETF (без доходностей): ETF_DATA_CAUSAL_PASS / BLOCKED_DATA.
Читает кэш снимков и ряды загрузчика. Метрики: пригодные дни, распределение задержки date → first_available, доля дат, впервые
увиденных только в слишком раннем снимке (< дата+30 ч), величина правок first → last, пропуски торговых дней.
Ворота — из PREREG_ETF_POTOK (A1): ≥ 300 дней BTC, медиана задержки ≤ 4 дн, расхождение сумм < 5%. Ослаблять нельзя."""
import datetime as dt, glob, json, sys
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "fabrika"))
import dannye_etf_potoki as E


def kvantili(x):
    x = sorted(x); n = len(x)
    return {q: round(x[min(n - 1, int(q / 100 * n))], 2) for q in (10, 50, 75, 90, 99)} if n else {}


def main():
    D = LAB / "data" / "etf_potoki"; out = {}
    for aktiv in ("btc", "eth"):
        fs = sorted(glob.glob(str(D / "snimki" / f"{aktiv}_*.html")))
        vidano_rano, vidano_pozdno = set(), set()
        for f in fs:
            ts = Path(f).stem.split("_")[1]; t = dt.datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc)
            tab, _ = E.razobrat(Path(f).read_bytes())
            for d in tab:
                (vidano_pozdno if t >= dt.datetime.fromisoformat(d).replace(tzinfo=dt.timezone.utc) + dt.timedelta(hours=30) else vidano_rano).add(d)
        p = D / f"{aktiv}.json"
        ryad = json.loads(p.read_text()) if p.exists() else []
        lag = [(r["available_ms"] - dt.datetime.fromisoformat(r["date"]).replace(tzinfo=dt.timezone.utc).timestamp() * 1000) / 86_400_000 for r in ryad]
        prav = [abs(r["last_total_musd"] - r["first_total_musd"]) for r in ryad]
        dni = [dt.date.fromisoformat(r["date"]) for r in ryad]
        budni = 0
        if dni:
            d = dni[0]
            while d <= dni[-1]:
                budni += d.weekday() < 5; d += dt.timedelta(days=1)
        out[aktiv] = dict(snimkov=len(fs), prigodnyh_dney=len(ryad), s=ryad[0]["date"] if ryad else None, po=ryad[-1]["date"] if ryad else None,
                          pokrytie_budney=round(len(ryad) / max(1, budni), 3), zaderzhka_dney=kvantili(lag),
                          tolko_rannie_snimki=len(vidano_rano - vidano_pozdno), dolya_tolko_rannih=round(len(vidano_rano - vidano_pozdno) / max(1, len(vidano_rano | vidano_pozdno)), 3),
                          dolya_pravok=round(sum(x > 0.05 for x in prav) / max(1, len(prav)), 3), pravki_musd=kvantili(prav))
    man = json.loads((D / "MANIFEST.json").read_text()) if (D / "MANIFEST.json").exists() else {}
    b = out["btc"]
    ok = (man.get("pravilo_versiya") == 2 and b["prigodnyh_dney"] >= 300 and (b["zaderzhka_dney"].get(50) or 99) <= 4
          and man.get("btc", {}).get("dolya_strok_s_raskhozhdeniem_summy", 1) < 0.05)
    out["VERDIKT"] = "ETF_DATA_CAUSAL_PASS" if ok else "BLOCKED_DATA"
    (D / "KACHESTVO.json").write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
