#!/usr/bin/env python3
"""digest.py — AUTONOMOUS_SHADOW_RESEARCH_V1, срез 2: детерминированная сводка состояния. ТОЛЬКО чтение, без сети, без доходностей.

    python3 research_lab/fabrika/digest.py            → data/digest/digest_<UTC>.json + digest_latest.json
Разделы: nabory (свежесть и покрытие наборов), zagruzki/teni (логи), prereg (замки и результаты), slot (активная гипотеза),
trevogi (по правилам ниже). Это вход для аналитика (срез 3) — он видит только этот файл, кладбище и каталог данных.
Правила тревог: набор отстаёт > 3 дн.; лог без «ГОТОВО» молчит > 60 мин (загрузки) / тень молчит > 180 мин;
prereg с замком без результата > 14 дн.; активных гипотез > 1; в логе Traceback/СТОП.
"""
from __future__ import annotations
import datetime as dt, json, re, sys
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
PODPAPKI = ("klines", "metrics", "taker", "funding")
ZAPRET_KLYUCHEY = re.compile(r"edge|bps|pnl|dohod|t_nw|syroy", re.I)   # в digest не должно быть доходностей


def poslednyaya_data(f: Path, pap: str):
    try:
        x = json.loads(f.read_text())
    except Exception:
        return None
    if pap == "metrics" and isinstance(x, dict) and x:
        return max(x)
    if isinstance(x, list) and x and isinstance(x[-1], list):
        return dt.datetime.fromtimestamp(int(x[-1][0]) / 1000, dt.timezone.utc).date().isoformat()
    return None


def nabory(data: Path, seychas: dt.datetime):
    out = {}
    for d in sorted(p for p in data.iterdir() if p.is_dir()):
        pod = {}
        for pap in PODPAPKI:
            fs = sorted((d / pap).glob("*.json")) if (d / pap).is_dir() else []
            if not fs:
                continue
            daty = [x for x in (poslednyaya_data(f, pap) for f in fs) if x]
            mx = max(daty) if daty else None
            pod[pap] = dict(faylov=len(fs), poslednyaya=mx,
                            otstavanie_dn=(seychas.date() - dt.date.fromisoformat(mx)).days if mx else None)
        if pod:
            pk = None
            if (d / "metrics").is_dir():
                met = {f.stem: json.loads(f.read_text()) for f in (d / "metrics").glob("*.json")}
                dni = sorted({k for v in met.values() for k in v})[-8:]
                pk = {k: sum(1 for v in met.values() if k in v and v[k] and v[k][-1]) for k in dni}
            out[d.name] = dict(podpapki=pod, monet_s_oi_poslednie_8_dat=pk)
    return out


def reestr(lab: Path) -> dict:
    f = lab / "fabrika" / "digest_nablyudenie.json"
    return json.loads(f.read_text()) if f.exists() else {"teni": {}, "arhivy": []}


def logi(data: Path, seychas: dt.datetime, teni: dict):
    out = {}
    kandidaty = [f for f in sorted(data.glob("*.log")) if seychas.timestamp() - f.stat().st_mtime < 48 * 3600 or "zagruzka" in f.name]
    for imya in teni:
        f = (data / imya).resolve()
        if f.exists() and f not in [k.resolve() for k in kandidaty]:
            kandidaty.append(f)
    for f in kandidaty:
        try:
            hvost = f.read_text(errors="replace").splitlines()[-200:]
        except Exception:
            continue
        posl = next((l for l in reversed(hvost) if l.strip()), "")
        klyuch = next((k for k in teni if (data / k).resolve() == f.resolve()), f.name)
        out[klyuch] = dict(minut_s_zapisi=int((seychas.timestamp() - f.stat().st_mtime) // 60),
                           gotovo=any("ГОТОВО" in l for l in hvost[-15:]),
                           oshibok=sum(1 for l in hvost if "Traceback" in l or "СТОП" in l),
                           posledniya_stroka=posl[:160] if f.suffix == ".log" else "",
                           vid="zagruzka" if "zagruzka" in f.name else ("ten" if klyuch in teni else "prochee"),
                           porog_min=teni.get(klyuch))
    return out


def prereg(lab: Path, seychas: dt.datetime):
    out = {}
    for p in sorted((lab / "prereg").glob("*.json")) if (lab / "prereg").is_dir() else []:
        sp = json.loads(p.read_text()); lock = p.with_suffix(".lock")
        kv = lab / "data" / "fabrika_xs" / sp.get("id", p.stem) / "KVITANCIYA.json"
        leg = sp.get("legacy_kvitanciya")
        status = json.loads(kv.read_text()).get("status") if kv.exists() else ("NASLEDIE_IZRASHODOVANO" if leg and (lab / leg).exists() else None)
        dn = None
        if lock.exists():
            dn = (seychas - dt.datetime.fromisoformat(json.loads(lock.read_text())["kogda"])).days
        out[sp.get("id", p.stem)] = dict(zamok=lock.exists(), dney_s_zamka=dn, rezultat=status is not None, status=status)
    return out


def sobrat(lab: Path = LAB, seychas: dt.datetime | None = None) -> dict:
    seychas = seychas or dt.datetime.now(dt.timezone.utc)
    data = lab / "data"
    rs = reestr(lab)
    nb, lg, pr = nabory(data, seychas), logi(data, seychas, rs["teni"]), prereg(lab, seychas)
    for n in rs["arhivy"]:
        if n in nb:
            nb[n]["arhiv"] = True
    sf = data / "fabrika_xs" / "SLOT.json"
    slot = json.loads(sf.read_text()) if sf.exists() else {"aktivnye": []}
    tr = []
    for n, v in nb.items():
        if v.get("arhiv"):
            continue
        for pap, x in v["podpapki"].items():
            if x["otstavanie_dn"] is not None and x["otstavanie_dn"] > 3:
                tr.append(f"набор {n}/{pap} отстаёт на {x['otstavanie_dn']} дн.")
    for n, v in lg.items():
        if v["oshibok"] and v["minut_s_zapisi"] < 48 * 60:
            tr.append(f"лог {n}: ошибок {v['oshibok']}")
        if v["vid"] == "zagruzka" and not v["gotovo"] and v["minut_s_zapisi"] > 60:
            tr.append(f"загрузка {n} молчит {v['minut_s_zapisi']} мин без ГОТОВО")
        if v["vid"] == "ten" and v["minut_s_zapisi"] > (v["porog_min"] or 180):
            tr.append(f"тень {n} молчит {v['minut_s_zapisi']} мин")
    for n, v in pr.items():
        if v["zamok"] and not v["rezultat"] and (v["dney_s_zamka"] or 0) > 14:
            tr.append(f"prereg {n}: замок {v['dney_s_zamka']} дн. без результата")
    if len(slot.get("aktivnye", [])) > 1:
        tr.append(f"активных гипотез {len(slot['aktivnye'])} > 1")
    dg = dict(kogda=seychas.isoformat(timespec="seconds"), nabory=nb, logi=lg, prereg=pr, slot=slot, trevogi=tr)
    if ZAPRET_KLYUCHEY.search(json.dumps(list(_klyuchi(dg)))):
        raise RuntimeError("в digest попали поля доходности — запрещено")
    return dg


def _klyuchi(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield k; yield from _klyuchi(v)
    elif isinstance(x, list):
        for v in x:
            yield from _klyuchi(v)


def main():
    dg = sobrat()
    out = LAB / "data" / "digest"; out.mkdir(parents=True, exist_ok=True)
    s = json.dumps(dg, ensure_ascii=False, indent=1)
    (out / f"digest_{dg['kogda'][:16].replace(':', '')}.json").write_text(s); (out / "digest_latest.json").write_text(s)
    print(f"digest: наборов {len(dg['nabory'])}, логов {len(dg['logi'])}, prereg {len(dg['prereg'])}, тревог {len(dg['trevogi'])}")
    for t in dg["trevogi"]:
        print("  ТРЕВОГА:", t)


if __name__ == "__main__":
    main()
