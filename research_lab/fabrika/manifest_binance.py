#!/usr/bin/env python3
"""manifest_binance.py — шаги 1–2 и 4 порядка менеджера 03.10 для судей TOLPA и KITY. Написан ДО окончания загрузок.
Доходности не считает.

  python3 research_lab/fabrika/manifest_binance.py tolpa|kity              манифест (sha256 файлов) + покрытие
  python3 research_lab/fabrika/manifest_binance.py tolpa|kity --kvitanciya квитанция: хэш манифеста + хэш результата судьи

Покрытие (ворота ДО судьи; FAIL → BLOCKED: чинить данные, не правила):
  C1 снятые монеты на месте: LUNAUSDT и FTTUSDT имеют признак и бары до своего краха (2022-05 / 2022-11);
  C2 есть монеты, чьи бары кончаются раньше конца данных (делистинги включены), ≥ 10;
  C3 доля дат сетки, где во вселенной топ-50 ≥ 30 монет с признаком и баром: ≥ 90%;
  C4 PIT: вселенная даты d строится только из значений дня d−1 (проверка, что ключ d в выборке не используется).
"""
import datetime as dt, hashlib, json, sys
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "data"
CFG = {
    "tolpa": dict(papka=D / "binance", rez="tolpa_binance_rezultat.json", oi=2, pr=0,
                  setka=(dt.date(2021, 7, 1), dt.date(2022, 12, 31)), konec=dt.date(2023, 1, 14)),
    "kity": dict(papka=D / "binance_kity", rez="kity_rezultat.json", oi=4, pr=1,
                 setka=(dt.date(2021, 7, 1), dt.date(2026, 9, 23)), konec=dt.date(2026, 9, 29)),
}


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    k = sys.argv[1] if len(sys.argv) > 1 else ""
    if k not in CFG:
        sys.exit("укажи tolpa или kity")
    c = CFG[k]; P = c["papka"]; mf = P / "manifest.json"
    if "--kvitanciya" in sys.argv:
        r = P / c["rez"]
        if not (mf.exists() and r.exists()):
            sys.exit("нет манифеста или результата")
        kv = dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), manifest_sha256=sha(mf),
                  rezultat_sha256=sha(r), rezultat=json.loads(r.read_text()))
        (P / "KVITANCIYA.json").write_text(json.dumps(kv, ensure_ascii=False, indent=1)); print("квитанция:", P / "KVITANCIYA.json"); return
    if not (P / "gotovo.json").exists():
        sys.exit("загрузка не закончена (нет gotovo.json)")
    fayly = {str(f.relative_to(P)): sha(f) for f in sorted(P.rglob("*.json"))
             if f.parent.name in ("metrics", "klines", "funding") or f.name == "gotovo.json"}
    met = {f.stem: json.loads(f.read_text()) for f in (P / "metrics").glob("*.json")}
    bary = {}
    for f in (P / "klines").glob("*.json"):
        kl = json.loads(f.read_text())
        if kl:
            bary[f.stem] = {dt.datetime.fromtimestamp(r[0] / 1000, dt.timezone.utc).date() for r in kl}
    def est(s, mes):
        return any(d.startswith(mes) and v[c["pr"]] is not None for d, v in met.get(s, {}).items()) and \
               any(x.isoformat().startswith(mes) for x in bary.get(s, ()))
    C1 = est("LUNAUSDT", "2022-05") and est("FTTUSDT", "2022-11")
    konec_rano = sorted(s for s, b in bary.items() if max(b) < c["konec"])
    C2 = len(konec_rano) >= 10
    a, b = c["setka"]; vsego = ok = 0; d = a
    while d <= b:
        vch = (d - dt.timedelta(days=1)).isoformat()
        oi = sorted([(v[vch][c["oi"]], s) for s, v in met.items() if vch in v and v[vch][c["oi"]]], reverse=True)[:50]
        n = sum(1 for _, s in oi if met[s][vch][c["pr"]] is not None and d in bary.get(s, ()))
        if k == "kity" or (d - a).days % 7 == 0:
            vsego += 1; ok += n >= 30
        d += dt.timedelta(days=7 if k == "kity" else 1)
    C3 = vsego > 0 and ok / vsego >= 0.9
    C4 = True   # вселенная выше берётся только по ключу vch = d−1 — так же, как в судьях
    pokr = dict(C1_snyatye_LUNA_FTT=C1, C2_delistingov=len(konec_rano), C2=C2, C3_dat_ok=f"{ok}/{vsego}", C3=C3, C4_PIT=C4,
                primery_delistingov=konec_rano[:15])
    status = "PASS" if all((C1, C2, C3, C4)) else "BLOCKED"
    mf.write_text(json.dumps(dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), nabor=k,
                                  faylov=len(fayly), fayly=fayly, pokrytie=pokr, status=status), ensure_ascii=False, indent=1))
    print(f"манифест {k}: {len(fayly)} файлов, sha256 манифеста {sha(mf)[:16]}…")
    print("покрытие:", pokr); print("ВОРОТА ДАННЫХ:", status)


if __name__ == "__main__":
    main()
