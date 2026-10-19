#!/usr/bin/env python3
"""alpaca_ii_veto_ten.py — хук сторожа: ТЕНЬ ИИ-одобрения покупок Monthly (PREREG_ALPACA_II_VETO_VPERED_2026_10_18,
дополнение 19.10). Только исследование: ордеров, параметров, ожидания денег — нет. Monthly ничего не ждёт.

Когда: по запечатанной ежедневной поставке Codex `data/alpaca_monthly58_daily_v1/<сессия>.json`, если в её диагностике
`monthly_calendar_due` = true (месячное решение замороженной Monthly). Один раз на сессию.
Что: кандидаты = бумаги top-18 по здоровью, прошедшие сетап (как у `select_v38_successor`), до 8 по оценке; выбор Monthly —
`hypothetical_monthly.picks`. Перед ИИ — паритет: пересчёт замороженной логикой обязан совпасть с диагностикой, иначе
PARITY_FAIL и ИИ не вызывается. Вход ИИ — только данные ≤ сессии (проверяется), новости/отчётность: НЕДОСТУПНЫ (честно
записывается; без них ИИ видит те же цены, что и селектор). Ресурсы — проверки ai_raund V2 (модель ≤ 8B, /api/ps пуст,
свободная память, замок, keep_alive 0, таймаут 120 с, дедлайн 300 с). Ollama/Mac недоступны → MISSING (не VETO).
Журнал `data/alpaca_ii_veto_zhurnal.jsonl` — только дописывается: записи `reshenie` (по кандидату) и позже `ishod`
(21/42 сессии, по мере наступления, из следующих поставок)."""
from __future__ import annotations
import datetime as dt, hashlib, json, math, sys, time
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(LAB / "factory_v3"))
SRC = LAB / "data" / "alpaca_monthly58_daily_v1"
ZH = LAB / "data" / "alpaca_ii_veto_zhurnal.jsonl"
MODEL, HOST = "qwen3:8b", "http://localhost:11434"
MAX_KAND, GORIZONTY = 8, (21, 42)
VERSIYA = "ii_veto_ten_v1"
KLIENT_TEST = None          # подмена клиента ИИ в тестах
SISTEMA = ("Ты — аналитик акций. Тебе дают кандидата, отобранного механической стратегией (покупка на откате в растущем "
           "тренде, удержание около месяца). Новостей и отчётности у тебя НЕТ — оценивай только по данным ниже. "
           "Ответь строго JSON: {\"reshenie\": \"APPROVE\" | \"VETO\" | \"ABSTAIN\", \"prichina\": \"до 300 знаков\", "
           "\"faktory\": [\"до 3 коротких факторов\"]}. VETO — только если в данных есть конкретная причина ожидать, что "
           "бумага в ближайший месяц будет хуже других кандидатов. Если данных недостаточно — ABSTAIN.")


def _sha_b(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha(p: Path) -> str:
    return _sha_b(p.read_bytes())


def zhurnal():
    return [json.loads(s) for s in ZH.read_text().splitlines() if s.strip()] if ZH.exists() else []


def zapisat(zapisi):
    if zapisi:
        with ZH.open("a") as f:
            for z in zapisi:
                f.write(json.dumps(z, ensure_ascii=False) + "\n")


def postavka(ses):
    f, p, g = SRC / f"{ses}.json", SRC / f"{ses}.delivery.json", SRC / f"{ses}.diagnostic.json"
    if not (f.exists() and p.exists() and g.exists()):
        return None, "NET_POSTAVKI"
    pech = json.loads(p.read_text()).get("files", {})
    if pech.get(f.name) != _sha(f) or pech.get(g.name) != _sha(g):
        return None, "SHA_NE_SOVPAL_S_PECHATYU"
    return (json.loads(f.read_text()), json.loads(g.read_text()), _sha(f), _sha(g)), None


def ryady(d, do_ses):
    from backtest.alpaca_exact_parity_contract import DailyBar
    return {s: [DailyBar(session_date=dt.date.fromisoformat(b["session"]), open=b["open"], high=b["high"], low=b["low"],
                         close=b["close"]) for b in sorted(bb, key=lambda x: x["session"]) if b["session"] <= do_ses]
            for s, bb in d["history"].items()}


def kandidaty(d, g):
    """Кандидаты по диагностике + паритет пересчётом замороженной логикой."""
    import backtest.alpaca_honest_portfolio as HP
    ses = d["session_date"]; R = ryady(d, ses)
    R = {s: r for s, r in R.items() if r and r[-1].session_date.isoformat() == ses}
    zd = {s: HP._universe_health(r) for s, r in R.items() if s not in ("SPY", "QQQ")}
    top = [s for s, v in sorted(((s, v) for s, v in zd.items() if math.isfinite(v)), key=lambda x: -x[1])[:18]]
    moi = {s: HP._v38_candidate(s, R[s]) for s in top}
    moi = {s: c.score for s, c in moi.items() if c is not None}
    diag = {x["symbol"]: x for x in g["stocks"]}
    ih = {s: x["candidate_score"] for s, x in diag.items() if x.get("candidate_pass") and (x.get("health_rank") or 99) <= 18}
    paritet = set(moi) == set(ih) and all(abs(moi[s] - ih[s]) < 1e-9 for s in moi)
    k = sorted(ih, key=lambda s: -ih[s])[:MAX_KAND]
    vybor = [p["symbol"] for p in (g.get("hypothetical_monthly") or {}).get("picks", [])]
    return k, ih, vybor, paritet, R


def vhod_ii(sym, R, diag, spy):
    r = R[sym][-60:]; c0 = r[-1].close
    m = diag.get("metrics", {})
    sp = R["SPY"]
    return {"tiker": sym, "sessiya": r[-1].session_date.isoformat(),
            "pokazateli_otbora": {k: round(v, 5) for k, v in m.items() if isinstance(v, (int, float))},
            "mesto_po_zdorovyu": diag.get("health_rank"), "ocenka_otbora": round(diag.get("candidate_score") or 0, 5),
            "zakrytiya_60d_v_pct_ot_poslednego": [round((b.close / c0 - 1) * 100, 2) for b in r],
            "rynok_SPY": {"dohod_20d_pct": round((sp[-1].close / sp[-21].close - 1) * 100, 2),
                          "dohod_60d_pct": round((sp[-1].close / sp[-61].close - 1) * 100, 2),
                          "vyshe_SMA200": bool(spy.get("gate_ok"))},
            "novosti_i_otchetnost": "НЕДОСТУПНЫ"}


def proverit_utechku(vhod, ses):
    assert vhod["sessiya"] <= ses, "в входе ИИ есть данные позже сессии решения"


def otkryt_vhoda_ms(d):
    for c in d.get("calendar", []):
        if c["session"] == d.get("entry_session"):
            return c["open_ms"]
    return None


def reshenie(ses, klient=None, proverki_fn=None, seychas_fn=None):
    """Одна сессия месячного решения → список записей. Ничего не пишет (пишет prohod)."""
    seychas_fn = seychas_fn or (lambda: dt.datetime.now(dt.timezone.utc))
    klient = klient or KLIENT_TEST
    pp, osh = postavka(ses)
    if osh:
        return [dict(tip="reshenie_sessii", sessiya=ses, status=osh, zapisano_utc=seychas_fn().isoformat(timespec="seconds"))]
    d, g, sha_d, sha_g = pp
    k, ih, vybor, paritet, R = kandidaty(d, g)
    baza = dict(sessiya=ses, entry_session=d.get("entry_session"), versiya=VERSIYA, istochnik_sha=sha_d, diagnostika_sha=sha_g,
                data_sha256=d.get("data_sha256"), market_data_asof=ses, source_available_ms=d.get("source_available_ms"),
                novosti="НЕДОСТУПНЫ", prompt_sha=_sha_b(SISTEMA.encode()), vybor_monthly=vybor, kandidaty=k)
    if not paritet:
        return [dict(baza, tip="reshenie_sessii", status="PARITY_FAIL", zapisano_utc=seychas_fn().isoformat(timespec="seconds"))]
    diag = {x["symbol"]: x for x in g["stocks"]}
    vhody = {s: vhod_ii(s, R, diag[s], g.get("spy_gate") or {}) for s in k}
    for v in vhody.values():
        proverit_utechku(v, ses)
    model_info, prichina_net, fd = None, None, None
    if klient is None:
        try:
            import ai_raund as AR, ai_kontrakt_v1 as A
            model_info = (proverki_fn or AR.proverki)(HOST, MODEL)
            tags = {m["name"]: m for m in AR._get(HOST, "/api/tags").get("models", [])}
            model_info["digest"] = tags.get(MODEL, {}).get("digest")
            fd = AR.zamok()
            klient = A.klient_ollama(MODEL, HOST, opcii=dict(num_predict=300), timeout_s=AR.TIMEOUT_S)
        except Exception as e:
            prichina_net = f"{type(e).__name__}: {str(e)[:200]}"
    vhod_ms = otkryt_vhoda_ms(d); t0 = time.time(); out = []
    for i, s in enumerate(k):
        zap = dict(baza, tip="reshenie", decision_id=f"{ses}:{s}", tiker=s, mesto_v_kandidatah=i + 1,
                   ocenka_otbora=ih[s], v_vybore_monthly=s in vybor, vhod_sha=_sha_b(json.dumps(vhody[s], sort_keys=True).encode()),
                   model=MODEL, model_info=model_info)
        if klient is None or time.time() - t0 > 300:
            zap.update(otvet="MISSING", prichina=prichina_net or "общий дедлайн 300 с исчерпан")
        else:
            try:
                o = klient(SISTEMA, json.dumps(vhody[s], ensure_ascii=False))
                r = str(o.get("reshenie", "")).upper()
                zap.update(otvet=r if r in ("APPROVE", "VETO", "ABSTAIN") else "ABSTAIN_NEVERNYY_OTVET",
                           prichina=str(o.get("prichina", ""))[:300], faktory=[str(x)[:80] for x in (o.get("faktory") or [])][:3])
            except Exception as e:
                zap.update(otvet="MISSING", prichina=f"ошибка модели: {type(e).__name__}: {str(e)[:150]}")
        t = seychas_fn(); zap["otvet_utc"] = t.isoformat(timespec="seconds")
        zap["do_otkrytiya_vhoda"] = bool(vhod_ms and t.timestamp() * 1000 < vhod_ms)
        out.append(zap)
    if model_info is not None:
        try:
            import ai_raund as AR; AR.vygruzit(HOST, MODEL)
        except Exception:
            pass
    if fd is not None:
        import os; os.close(fd)                       # замок ai_raund освобождается сразу (сторож живёт часами)
    return out


def ishody(Z):
    """Дописать исходы 21/42 сессии, когда последующие поставки их содержат. Доходность: открытие сессии входа →
    закрытие h-й сессии; относительная — минус среднее по кандидатам того же решения."""
    est = {(z["decision_id"], z["gorizont"]) for z in Z if z.get("tip") == "ishod"}
    resh = [z for z in Z if z.get("tip") == "reshenie"]
    if not resh:
        return []
    posl = sorted(SRC.glob("20??-??-??.json"))
    if not posl:
        return []
    d = json.loads(posl[-1].read_text()); H = d["history"]; out = []
    po_ses = {}
    for z in resh:
        po_ses.setdefault(z["sessiya"], []).append(z)
    for ses, zz in po_ses.items():
        vh = zz[0]["entry_session"]
        for h in GORIZONTY:
            doh = {}
            for z in zz:
                bb = sorted((b for b in H.get(z["tiker"], []) if b["session"] >= vh), key=lambda b: b["session"])
                if len(bb) >= h:
                    doh[z["tiker"]] = bb[h - 1]["close"] / bb[0]["open"] - 1
            if len(doh) < len(zz):
                continue
            sr = sum(doh.values()) / len(doh)
            for z in zz:
                if (z["decision_id"], h) not in est:
                    out.append(dict(tip="ishod", decision_id=z["decision_id"], gorizont=h, dohod=doh[z["tiker"]],
                                    otnositelno_kandidatov=doh[z["tiker"]] - sr, istochnik_sha=_sha(posl[-1]),
                                    zapisano_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
    return out


def prohod():
    Z = zhurnal(); sdelano = {z["sessiya"] for z in Z if z.get("tip") in ("reshenie", "reshenie_sessii")}
    novye = []
    for g in sorted(SRC.glob("20??-??-??.diagnostic.json")):
        ses = g.name[:10]
        if ses in sdelano:
            continue
        try:
            due = json.loads(g.read_text()).get("monthly_calendar_due")
        except Exception:
            continue
        if due:
            r = reshenie(ses)
            vse_missing = r and all(z.get("otvet") == "MISSING" for z in r if z.get("tip") == "reshenie")
            vhod_ms = next((z for z in r if z.get("tip") == "reshenie"), {}).get("do_otkrytiya_vhoda")
            if vse_missing and vhod_ms:               # Ollama/Mac недоступны, но вход ещё не открылся — повторим на следующем проходе
                continue
            novye += r
    zapisat(novye)
    ish = ishody(zhurnal()); zapisat(ish)
    return {"resheniy": sum(1 for z in novye if z.get("tip") == "reshenie"), "sessiy": sorted({z["sessiya"] for z in novye}),
            "otvety": sorted({z.get("otvet") or z.get("status") for z in novye}), "ishodov": len(ish)}


if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False))
