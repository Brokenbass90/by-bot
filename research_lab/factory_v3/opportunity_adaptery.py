#!/usr/bin/env python3
"""opportunity_adaptery.py — переводчики живых ног в OpportunityRecord V1. ТОЛЬКО ЧТЕНИЕ их данных (14.10.2026).
Ничего не пишет в тени/сборщики; результат — data/opportunities/<НОГА>.csv.gz (+ схема).

  kity_bybit()  — тень KITY Bybit: signal.json (решение после 00:10 UTC дня d по потоку d−1) + vhod/vyhod (закрытие d / d+7).
  elder()       — ядро ETS2M: vhody (сигналы источника ETS2S) + ishody (R по двигателям 24H/WIDE/CONTROL);
                  время решения = первая запись источника ten_ETS2S.jsonl; доход в долях ≈ R × stop_dolya.
  liq_v2(put)   — события PREREG_LIQ_OTSKOK_4H_V2 из ленты V2 Codex (нормализованные записи JSONL) — без цен и исходов.
    python3 research_lab/factory_v3/opportunity_adaptery.py [kity|elder|liq <путь_к_V2.jsonl>]
"""
import datetime as dt, json, sys
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent; LAB = HERE.parent; D = LAB / "data"; OPP = D / "opportunities"
sys.path.insert(0, str(HERE))
import opportunity_v1 as O       # noqa: E402

H, DEN = 3_600_000, 86_400_000; KOM = 12e-4


def _jl(p):
    p = Path(p)
    if not p.exists(): return []
    with open(p) as f: return [json.loads(l) for l in f if l.strip()]


def _ms(d): return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)


def kity_bybit(papka=D / "kity_bybit_ten"):
    out = []
    for dp in sorted(Path(papka).glob("20*")):
        sig = dp / "signal.json"
        if not sig.exists(): continue
        s = json.loads(sig.read_text()); d = dt.date.fromisoformat(s["d"])
        vh = json.loads((dp / "vhod.json").read_text()) if (dp / "vhod.json").exists() else None
        vy = json.loads((dp / "vyhod.json").read_text()) if (dp / "vyhod.json").exists() else None
        vyh = {(n["s"], n["side"]): n for n in (vy or {}).get("nogi", [])}
        t_res = int(dt.datetime.fromisoformat(s["vychisleno"]).timestamp() * 1000)
        for side, nogi in ((1, s["long"]), (-1, s["short"])):
            for n in nogi:
                p = next((x for x in (vh or {}).get("pozicii", []) if x["s"] == n["s"] and x["side"] == side), {})
                v = vyh.get((n["s"], side), {})
                out.append(O.zapis(t_res, _ms(d) - 1, max(t_res, _ms(d) + DEN - 1), n["s"], "KITY_BYBIT", "ten_v1", side,
                                   p.get("cena_vhoda"), KOM, dict(taker=n["taker"], monet=s["monet_s_priznakom"]),
                                   (_ms(d + dt.timedelta(days=7)) + DEN - 1) if v else None, v.get("cena_vyhoda"),
                                   (-side * v["fanding"]) if v.get("fanding") is not None else None, v.get("dohod")))
    O.zapisat(OPP / "KITY_BYBIT.csv.gz", out); return len(out)


def elder():
    perv = {}
    for r in _jl(D / "ten_ETS2S.jsonl"): perv.setdefault((r["sym"], int(r["ts"])), r)
    ish = defaultdict(dict)
    for r in _jl(D / "yadro" / "ETS2M" / "ishody.jsonl"): ish[r["id"]][r["dvigatel"]] = r
    out = []
    for v in _jl(D / "yadro" / "ETS2M" / "vhody.jsonl"):
        src = perv.get((v["sym"], int(v["ts"])))
        t_res = int(src["zapisano"]) if src else int(v["ts"])
        side = 1 if v["side"] in ("long", "Buy") else -1
        for dvig, x in ish.get(v["id"], {}).items():
            out.append(O.zapis(max(t_res, int(v["ts"])), int(v["ts"]), max(t_res, int(v["ts"])), v["sym"], f"ELDER_ETS2M_{dvig}", "v2", side,
                               None, float(x.get("izderzhki_R", 0)) * v["stop_dolya"],
                               dict(stop_dolya=v["stop_dolya"], rr1=x.get("rr1"), rr2=x.get("rr2"), hold=x.get("hold"),
                                    vovremya=bool(src and src["zapisano"] - v["ts"] <= 6 * H)),
                               max(t_res, int(v["ts"])) + 1 + int(x.get("barov", 0)) * H, None, None, float(x["R"]) * v["stop_dolya"]))
    O.zapisat(OPP / "ELDER_ETS2M.csv.gz", out); return len(out)


def liq_v2(put, prog_dney=14, porog_usd=50_000, dominir=3.0, zapas_ms=120_000, dyry=(), epoha=None, min_izvestno=0.8):
    """События PREREG_LIQ_OTSKOK_4H_V2 (BASE) + ПОПРАВКА A1: эпоха, дыры = UNKNOWN (не ноль), дубликаты по canonical sha один раз,
    опоздание по t_available_ms. Только лента V2; цены/исходы не читаются. dyry = [(начало_мс, конец_мс), ...] из heartbeat Codex."""
    chas = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0])); qa = dict(pozdnie=0, dubli=0, chuzhaya_epoha=0, bez_chasov=0)
    vid = set()
    for e in _jl(put):
        if e.get("schema", "BYBIT_ALL_LIQUIDATION_SOURCE_V2") != "BYBIT_ALL_LIQUIDATION_SOURCE_V2": continue
        if epoha and e.get("epoch", e.get("epoha")) not in (None, epoha): qa["chuzhaya_epoha"] += 1; continue
        if e.get("clock_status") == "UNKNOWN": qa["bez_chasov"] += 1; continue
        k = e.get("raw_item_canonical_sha256")
        if k:
            if k in vid: qa["dubli"] += 1; continue
            vid.add(k)
        h = e["ts_ms"] // H * H; dost = e.get("t_available_ms", e.get("recv_ts_ms"))
        if dost is not None and dost > h + H + zapas_ms: qa["pozdnie"] += 1; continue
        chas[e["symbol"]][h][0 if e["side"] == "long" else 1] += float(e["usd"])
    def v_dyre(h): return any(a < h + H and b > h for a, b in dyry)
    out = []
    for s, ser in chas.items():
        hs = sorted(ser); h0 = hs[0]; okno = prog_dney * 24
        vse = list(range(h0, hs[-1] + H, H)); L = {h: ser.get(h, [0.0, 0.0]) for h in vse}
        neizv = {h for h in vse if v_dyre(h)}
        poka = -1
        for k, h in enumerate(vse):
            if k < okno or h <= poka or h in neizv: continue
            ist_h = [x for x in vse[k - okno:k] if x not in neizv]
            if len(ist_h) < min_izvestno * okno: continue
            for ind, side in ((0, 1), (1, -1)):
                tek, prot = L[h][ind], L[h][1 - ind]
                if tek < porog_usd or tek < dominir * prot: continue
                ist = sorted(L[x][ind] for x in ist_h); p99 = ist[int(0.99 * (len(ist) - 1))]
                if tek < p99: continue
                t_res = h + H + zapas_ms
                out.append(O.zapis(t_res, h + H - 1, t_res, s, "LIQ_OTSKOK_4H_V2", "BASE", side, None, KOM,
                                   dict(L_long=round(L[h][0], 2), L_short=round(L[h][1], 2), p99_14d=round(p99, 2))))
                poka = h + 4 * H; break
    O.zapisat(OPP / "LIQ_OTSKOK_4H_V2.csv.gz", out); return len(out), qa


if __name__ == "__main__":
    a = sys.argv[1:] or ["kity", "elder"]
    if "kity" in a: print("KITY_BYBIT:", kity_bybit())
    if "elder" in a: print("ELDER_ETS2M:", elder())
    if "liq" in a: print("LIQ_OTSKOK_4H_V2 (событий, QA):", liq_v2(a[a.index("liq") + 1]))
