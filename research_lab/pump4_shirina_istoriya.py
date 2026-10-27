#!/usr/bin/env python3
"""pump4_shirina_istoriya.py — prereg/PREREG_PUMP4_SHIRINA_ISTORIYA_2026_10_27.md (27.10.2026, Claude).
    python3 research_lab/pump4_shirina_istoriya.py e1   # история 2023-03..2025-09 (те же сделки, что Э1 REZHIM_V1)
    python3 research_lab/pump4_shirina_istoriya.py e2   # запечатанное 2025-10-01..2026-08-11 — только при PASS e1
Повтор — pump4_rezhim_zamer.odna_moneta с теми же seed; ширина = сигналы всех монет в [ts − 24 ч; ts)."""
import collections, glob, hashlib, json, os, sys, time
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import pump4_rezhim_zamer as Z
PREREG = HERE / "prereg" / "PREREG_PUMP4_SHIRINA_ISTORIYA_2026_10_27.md"
PREREG_SHA = "48269bd463e31642c93310d9c322c0e99195f2d9b948d967d52a63195d4a2e1e"
H = Z.H

def kvartal(t): g = time.gmtime(t / 1000); return f"{g.tm_year}-Q{(g.tm_mon - 1) // 3 + 1}"

def butstrap(sd, n=2000, seed=27):
    ned = collections.defaultdict(list)
    for x in sd: ned[x["ts"] // (7 * 86400000)].append((not x["otrez"], x["R"] - x["ctrl"]))
    keys = list(ned); rng = np.random.default_rng(seed)
    def razn(ws):
        a = [v for w in ws for f, v in ned[w] if f]; b = [v for w in ws for f, v in ned[w] if not f]
        return (np.mean(a) - np.mean(b)) if a and b else None
    base = razn(keys); res = np.array([r for r in (razn([keys[i] for i in rng.integers(0, len(keys), len(keys))]) for _ in range(n)) if r is not None])
    return dict(raznica=round(float(base), 4) if base is not None else None, q05=round(float(np.quantile(res, 0.05)), 4),
                dolya_le0=round(float((res <= 0).mean()), 4), nedel=len(keys))

def gruppy(sd):
    return dict(vzyat=Z.svod([x for x in sd if not x["otrez"]]), otrezano=Z.svod([x for x in sd if x["otrez"]]),
                dolya_otrezano=round(sum(x["otrez"] for x in sd) / len(sd), 3) if sd else None)

def main():
    if hashlib.sha256(PREREG.read_bytes()).hexdigest() != PREREG_SHA: sys.exit("prereg изменён")
    etap = sys.argv[1]; start, cut = Z.OKNA[etap]
    if etap == "e2":
        f1 = sorted(glob.glob(str(HERE / "results" / "pump4_shirina_e1_*.json")))
        if not f1 or json.load(open(f1[-1]))["verdikt"]["itog"] != "PASS": sys.exit("e2 запрещён: нет PASS e1")
    syms = json.load(open(HERE / "data" / "pump4_v1_universe_20261020.json"))["symbols"]
    os.environ[f"{Z.P.PFX}_SYMBOL_ALLOWLIST"] = ",".join(syms)
    vse = []
    for k, s in enumerate(syms):
        _, sd, _ = Z.odna_moneta((s, start, cut, 20261027 + k)); vse += sd or []
    tsa = sorted(x["ts"] for x in vse)
    import bisect
    for x in vse: x["shirina"] = bisect.bisect_left(tsa, x["ts"]) - bisect.bisect_left(tsa, x["ts"] - 24 * H)
    zb = np.load(HERE / "data" / "h1" / "BTCUSDT.npz"); bts = zb["ts"].astype(np.int64); m = bts < cut
    mt = Z.metki_btc(bts[m], zb["ohlcv"].astype(float)[m])
    z = [x for x in vse if x["status"] == "ZAKRYTA"]
    for x in z: x["otrez"] = x["shirina"] >= 3; x["rezhim"] = mt.get(x["ts"], "UNKNOWN")
    out = dict(etap=etap, signalov=len(vse), zakryto=len(z), vse=Z.svod(z), **gruppy(z), butstrap=butstrap(z),
               po_shirine={k: Z.svod([x for x in z if lo <= x["shirina"] <= hi]) for k, (lo, hi) in
                           {"0": (0, 0), "1-2": (1, 2), "3-5": (3, 5), "6+": (6, 10 ** 6)}.items()},
               peresechenie_s_rezhimom={r: gruppy([x for x in z if (x["rezhim"] == "BULL_TREND") == (r == "BULL")]) for r in ("BULL", "ne_BULL")})
    if etap == "e1":
        f0 = sorted(glob.glob(str(HERE / "results" / "pump4_rezhim_e1_*.json")))[-1]
        et = {(x["sym"], x["ts"]): x["R"] for x in json.load(open(f0))["sdelki"]}
        out["parity_s_E1"] = dict(etalon=len(et), sovpalo=sum(1 for x in z if et.get((x["sym"], x["ts"])) == x["R"]))
        out["po_oknam"] = {k: dict(**gruppy(g), butstrap=butstrap(g)) for k, (a, b) in Z.POD["e1"].items()
                           for g in [[x for x in z if a <= x["ts"] < b]]}
        kv = sorted({kvartal(x["ts"]) for x in z}); loqo = {}
        for q in kv:
            g = [x for x in z if kvartal(x["ts"]) != q]; a = [x["R"] for x in g if not x["otrez"]]; b = [x["R"] for x in g if x["otrez"]]
            loqo[q] = round(float(np.mean(a) - np.mean(b)), 4) if a and b else None
        out["bez_kvartala_raznica"] = loqo
        out["po_kvartalam"] = {q: gruppy([x for x in z if kvartal(x["ts"]) == q]) for q in kv}
        v, b_, bs = out["vzyat"], out["otrezano"], out["butstrap"]
        crit = dict(a_n=v["n"] >= 30 and b_.get("n", 0) >= 30,
                    b_butstrap=(bs["raznica"] or 0) > 0 and bs["dolya_le0"] <= 0.05,
                    v_oba_okna=all((w["butstrap"]["raznica"] or 0) > 0 for w in out["po_oknam"].values()),
                    g_otrezannye_le0=b_.get("n", 0) > 0 and b_["sred_R"] <= 0,
                    d_bez_lyubogo_kvartala=all(r is not None and r > 0 for r in loqo.values()))
    else:
        v, b_, bs = out["vzyat"], out["otrezano"], out["butstrap"]; a = v["n"] >= 20 and b_.get("n", 0) >= 20
        crit = dict(a_n=a, b_luchshe=a and v["sred_R"] > b_["sred_R"], v_otrez_le0=a and b_["sred_R"] <= 0, g_butstrap=bs["dolya_le0"] <= 0.10)
    crit["itog"] = "PASS" if all(crit.values()) else "FAIL"; out["verdikt"] = crit
    out.update(kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), prereg_sha256=PREREG_SHA,
               kod_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), sdelki=z)
    f = HERE / "results" / time.strftime(f"pump4_shirina_{etap}_%Y%m%dT%H%MZ.json", time.gmtime())
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "sdelki"}, ensure_ascii=False, indent=1)); print("файл:", f)

if __name__ == "__main__": main()
