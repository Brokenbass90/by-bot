#!/usr/bin/env python3
"""sudya_xs.py — AUTONOMOUS_SHADOW_RESEARCH_V1, срез 1: обобщённый детерминированный судья поперечных недельных механизмов.

Предрегистрация — JSON (research_lab/prereg/<id>.json), замок — <id>.lock с sha256 JSON.
    python3 research_lab/fabrika/sudya_xs.py zamorozit research_lab/prereg/<id>.json
    python3 research_lab/fabrika/sudya_xs.py progon    research_lab/prereg/<id>.json
Гарантии (проверяются ДО загрузки данных):
  * прогон только при замке и совпадении sha256 (правка JSON после заморозки → отказ);
  * повторный прогон запрещён: есть результат/квитанция в выходной папке или квитанция наследия (legacy_kvitanciya) → отказ;
  * признаки — только из белого списка (никакого кода из JSON): metrics[i] (d−1), taker_share (d−1), ret_1d (d−1),
    ret_7d (закрытие d−1 к d−8), taker_7d (средняя доля тейкеров d−7…d−1), ost_ret7_taker7 (поперечный остаток ret_7d
    после регрессии на taker_7d по монетам даты — «ход без потока», 05.10);
  * результат и квитанция пишутся один раз (sha256 prereg, данных и результата).
Логика сделки = kity_sudya / kity_m3_sudya: PIT топ-N по OI d−1, ≥ min_istoriya баров, децили, удержание, фандинг,
издержки, выход по последнему закрытию при исчезновении монеты, itog с t Ньюи–Уэста (лаг 1).
"""
from __future__ import annotations
import datetime as dt, hashlib, json, sys
from pathlib import Path
import numpy as np

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB))
import discovery_paket1 as P  # noqa: E402

DEN = 86_400_000
PRIZNAKI = {"metrics", "taker_share", "ret_1d", "ret_7d", "taker_7d", "ost_ret7_taker7", "oi_7d", "ret7_pri_roste_oi"}
OBYAZ = ("id", "dannye", "okna", "setka", "vselennaya", "priznak", "znak", "hold", "izderzhki_bps", "porogi")


class Otkaz(Exception):
    pass


def sha_b(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def den(t) -> dt.date: return dt.datetime.fromtimestamp(int(t) / 1000, dt.timezone.utc).date()
def ms(d: dt.date) -> int: return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
def D(s: str) -> dt.date: return dt.date.fromisoformat(s)


def proverit_spec(sp: dict):
    for k in OBYAZ:
        if k not in sp:
            raise Otkaz(f"в prereg нет поля {k}")
    for pr in [sp["priznak"]] + [k["priznak"] for k in sp.get("kontroli", [])]:
        if pr.get("tip") not in PRIZNAKI:
            raise Otkaz(f"признак {pr.get('tip')} не из белого списка {sorted(PRIZNAKI)}")
    if "PRIMARY" not in sp["okna"]:
        raise Otkaz("нет окна PRIMARY")


def puti(prereg: Path, sp: dict, baza: Path):
    vyh = baza / "data" / "fabrika_xs" / sp["id"]
    return prereg.with_suffix(".lock"), vyh / "rezultat.json", vyh / "KVITANCIYA.json"


def zamorozit(prereg: Path, baza: Path = LAB) -> str:
    b = prereg.read_bytes(); sp = json.loads(b); proverit_spec(sp)
    lock, rez, kv = puti(prereg, sp, baza)
    if lock.exists():
        raise Otkaz(f"замок уже есть: {lock}")
    if rez.exists() or kv.exists():
        raise Otkaz("результат уже существует — замораживать поздно")
    h = sha_b(b)
    lock.write_text(json.dumps(dict(sha256=h, kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")), indent=1))
    return h


def proverki_do_dannyh(prereg: Path, baza: Path = LAB):
    b = prereg.read_bytes(); sp = json.loads(b); proverit_spec(sp)
    lock, rez, kv = puti(prereg, sp, baza)
    if not lock.exists():
        raise Otkaz("нет замка: сначала zamorozit (до данных)")
    if json.loads(lock.read_text())["sha256"] != sha_b(b):
        raise Otkaz("sha256 prereg не совпадает с замком — prereg правили после заморозки")
    if rez.exists() or kv.exists():
        raise Otkaz("результат уже есть — повторный прогон запрещён")
    leg = sp.get("legacy_kvitanciya")
    if leg and (baza / leg).exists():
        raise Otkaz(f"исход уже израсходован (квитанция наследия {leg}) — повторный прогон запрещён")
    return sp, sha_b(b), rez, kv


def zagruzit(papka: Path):
    M = {}
    for f in sorted((papka / "klines").glob("*.json")):
        kl = np.array(json.loads(f.read_text()), dtype=float)
        if len(kl) < 61:
            continue
        fp = papka / "funding" / f.name
        fr = np.array((json.loads(fp.read_text()) if fp.exists() else []) or [[0, 0.0]], dtype=float)
        mp = papka / "metrics" / f.name
        tp = papka / "taker" / f.name
        tk = {}
        if tp.exists():
            for t, qv, tq in json.loads(tp.read_text()):
                if qv > 0:
                    tk[den(t).isoformat()] = tq / qv
        M[f.stem] = dict(ts=kl[:, 0].astype(np.int64), c=kl[:, 4], fts=fr[:, 0].astype(np.int64), fr=fr[:, 1],
                         met=json.loads(mp.read_text()) if mp.exists() else {}, taker=tk)
    return M


def otpechatok(papka: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(papka.rglob("*.json")):
        if f.parent.name in ("klines", "funding", "metrics", "taker"):
            h.update(f.name.encode()); h.update(f.read_bytes())
    return h.hexdigest()


def sdelka(x, i, hold, side, kom, data_do):
    t_vyh = int(x["ts"][i]) + hold * DEN
    j = int(np.searchsorted(x["ts"], t_vyh, side="right")) - 1
    if j <= i:
        return None
    if x["ts"][j] != t_vyh and den(x["ts"][-1]) >= data_do - dt.timedelta(days=1):
        return None
    return side * (x["c"][j] / x["c"][i] - 1) - side * P.fand(x, x["ts"][i], x["ts"][j]) - kom


def znachenie(pr, x, i, vch):
    if pr["tip"] == "metrics":
        v = x["met"].get(vch); return v[pr["indeks"]] if v else None
    if pr["tip"] == "taker_share":
        return x["taker"].get(vch)
    if pr["tip"] == "ret_1d":
        return (x["c"][i - 1] / x["c"][i - 2] - 1) if x["ts"][i] - x["ts"][i - 1] == DEN else None
    if pr["tip"] == "ret_7d":
        return (x["c"][i - 1] / x["c"][i - 8] - 1) if x["ts"][i - 1] - x["ts"][i - 8] == 7 * DEN else None
    if pr["tip"] == "taker_7d":
        d0 = den(x["ts"][i]); v = [x["taker"].get((d0 - dt.timedelta(days=k)).isoformat()) for k in range(1, 8)]
        return float(np.mean(v)) if all(z is not None for z in v) else None
    if pr["tip"] == "oi_7d":                      # лог-изменение OI в КОНТРАКТАХ (OI $ / закрытие того же дня), d−8 → d−1
        v1 = x["met"].get(vch); v0 = x["met"].get((dt.date.fromisoformat(vch) - dt.timedelta(days=7)).isoformat())
        if not (v1 and v0 and v1[4] and v0[4]) or x["ts"][i - 1] - x["ts"][i - 8] != 7 * DEN:
            return None
        return float(np.log(v1[4] / x["c"][i - 1]) - np.log(v0[4] / x["c"][i - 8]))
    if pr["tip"] == "ret7_pri_roste_oi":          # ret_7d, если OI вырос; иначе 0 (ход без новых денег — нейтрален), 05.10
        r, o = znachenie({"tip": "ret_7d"}, x, i, vch), znachenie({"tip": "oi_7d"}, x, i, vch)
        return None if r is None or o is None else (r if o > 0 else 0.0)
    if pr["tip"] == "ost_ret7_taker7":            # пара (ret_7d, taker_7d); остаток считается поперечно в nedelya
        a, b = znachenie({"tip": "ret_7d"}, x, i, vch), znachenie({"tip": "taker_7d"}, x, i, vch)
        return None if a is None or b is None else (a, b)
    raise Otkaz("признак вне белого списка")


def schitat(sp: dict, M: dict) -> dict:
    v = sp["vselennaya"]; oi_i = v.get("oi_indeks", 4); top = v.get("top", 50)
    min_m = v.get("min_monet", 30); min_ist = v.get("min_istoriya", 60)
    hold = sp["hold"]; kom = sp["izderzhki_bps"] / 1e4
    data_do = D(sp.get("data_do", "2026-09-30"))
    setka = [D(sp["setka"]["ot"]) + dt.timedelta(days=sp["setka"].get("shag", 7) * k) for k in range(2000)]

    def nedelya(d, pr, znak):
        vch = (d - dt.timedelta(days=1)).isoformat()
        oi = sorted([(x["met"][vch][oi_i], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][oi_i]], reverse=True)[:top]
        rows = []
        for _, s in oi:
            x = M[s]; i = int(np.searchsorted(x["ts"], ms(d)))
            if i >= len(x["ts"]) or x["ts"][i] != ms(d) or i < min_ist:
                continue
            z = znachenie(pr, x, i, vch)
            if z is not None and (isinstance(z, tuple) or np.isfinite(z)):
                rows.append((z, s, i))
        if len(rows) < min_m:
            return None
        if pr["tip"] == "ost_ret7_taker7":
            y = np.array([z[0] for z, _, _ in rows]); xx = np.array([z[1] for z, _, _ in rows])
            A = np.vstack([np.ones(len(xx)), xx]).T; beta = np.linalg.lstsq(A, y, rcond=None)[0]
            rows = [(float(y[k] - A[k] @ beta), s, i) for k, (_, s, i) in enumerate(rows)]
        rows.sort(); k = len(rows) // 10
        leg = [sdelka(M[s], i, hold, -znak, kom, data_do) for _, s, i in rows[:k]] + \
              [sdelka(M[s], i, hold, +znak, kom, data_do) for _, s, i in rows[-k:]]
        leg = [r for r in leg if r is not None]
        return float(np.mean(leg)) if leg else None

    def okno(a, b, pr, znak):
        return [(ms(d), r, None) for d in setka if D(a) <= d <= D(b) for r in [nedelya(d, pr, znak)] if r is not None]

    por = sp["porogi"]; rez = {}; serii = {}
    for imya, (a, b) in sp["okna"].items():
        s = okno(a, b, sp["priznak"], sp["znak"]); serii[imya] = s
        it = P.itog(s, s_kontrolem=False, lag=1)
        if it["verdikt"] == "SURVIVED" and (it.get("t", 0) < por.get("t_nw", 2.0) or it.get("dney", 0) < por.get("min_nedel", 52)):
            it["verdikt"] = "KILLED"; it["prichina"] = "порог t/недель prereg"
        if imya != "PRIMARY":
            it["status"] = ("BLOCKED_DATA" if it.get("n", 0) < 20 else ("CROSS_PERIOD_PASS" if it["verdikt"] == "SURVIVED" else
                            ("SAME_SIGN" if it.get("edge_bps", 0) > 0 else "OPPOSITE")))
        rez[imya] = it
    vse = dict((t, r) for s in serii.values() for t, r, _ in s)
    nez = {}
    for k in sp.get("kontroli", []):
        d2 = dict((t, r) for a, b in sp["okna"].values() for t, r, _ in okno(a, b, k["priznak"], k["znak"]))
        para = [(vse[t], d2[t]) for t in vse if t in d2]
        kor = round(float(np.corrcoef(*zip(*para))[0, 1]), 2) if len(para) > 10 else None
        nez[k["imya"]] = dict(korr=kor, nedel=len(para), ok=kor is not None and abs(kor) < k["porog_abs_korr"])
    rez["nezavisimost"] = nez
    pr_ok = rez["PRIMARY"]["verdikt"] == "SURVIVED"
    opp = any(v.get("status") == "OPPOSITE" for k2, v in rez.items() if k2 not in ("PRIMARY", "nezavisimost"))
    nez_ok = all(v["ok"] for v in nez.values())
    rez["status"] = ("KILL" if not pr_ok else "PRIMARY_PASS_BUT_REPLICATION_OPPOSITE" if opp else
                     "PRIMARY_PASS_BUT_NOT_INDEPENDENT" if not nez_ok else "READY_FOR_BUILD")
    return rez


def progon(prereg: Path, baza: Path = LAB) -> dict:
    sp, h_pr, rez_p, kv_p = proverki_do_dannyh(prereg, baza)
    papka = baza / "data" / sp["dannye"]
    M = zagruzit(papka)
    rez = schitat(sp, M)
    rez_p.parent.mkdir(parents=True, exist_ok=True)
    rez_p.write_text(json.dumps(dict(id=sp["id"], prereg_sha256=h_pr, rezultat=rez), ensure_ascii=False, indent=1))
    kv_p.write_text(json.dumps(dict(id=sp["id"], prereg_sha256=h_pr, dannye_sha256=otpechatok(papka),
                                    rezultat_sha256=sha_b(rez_p.read_bytes()), status=rez["status"],
                                    kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")), ensure_ascii=False, indent=1))
    return rez


if __name__ == "__main__":
    try:
        kmd, pth = sys.argv[1], Path(sys.argv[2])
        if kmd == "zamorozit":
            print("замок:", zamorozit(pth))
        elif kmd == "progon":
            print(json.dumps(progon(pth), ensure_ascii=False, indent=1))
        else:
            raise Otkaz("команда: zamorozit | progon")
    except Otkaz as e:
        sys.exit(f"ОТКАЗ: {e}")
