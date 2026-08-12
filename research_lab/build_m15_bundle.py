#!/usr/bin/env python3
"""build_m15_bundle.py — 5m JSON -> 15-минутные серии, потоково и с бюджетом.

Тот же приём, что и в build_h1_bundle.py: файл читается, сразу
сворачивается в 15 минут и отпускается. Ничего крупнее одного файла
в памяти не живёт. Работает по списку символов (аллоулист V2).

Резюмируемость: уже готовые .npz пропускаются, поэтому скрипт можно
запускать повторно, пока не пройдёт весь список. Бюджет времени
в секундах — переменная M15_BUDGET_S.
"""
import io, os, sys, glob, re, time, json, gc, tempfile
import numpy as np
import pandas as pd

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
ALLOW = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else None
CACHE = os.path.join(ROOT, "data_cache")
OUTDIR = os.getenv("M15_OUTDIR") or os.path.join(ROOT, "research_lab", "data", "m15")
os.makedirs(OUTDIR, exist_ok=True)
STATUS_PATH = os.getenv("M15_STATUS_PATH") or os.path.join(OUTDIR, "build_status.json")
BUDGET = float(os.getenv("M15_BUDGET_S", "600"))
FORCE_REFRESH = str(os.getenv("M15_FORCE_REFRESH", "0")).strip().lower() in {
    "1", "true", "yes", "on"
}
STEP = 900_000
MIN_BARS = 96 * 45

pat = re.compile(r"^(?P<sym>[A-Z0-9]+USDT)_5_.*\.json$")
files_by_sym = {}
for fp in glob.glob(os.path.join(CACHE, "*.json")):
    m = pat.match(os.path.basename(fp))
    if not m: continue
    s = m.group("sym")
    if ALLOW and s not in ALLOW: continue
    files_by_sym.setdefault(s, []).append(fp)

t0 = time.time()
done = skipped = 0
budget_exhausted = False
status = {
    "schema": "mpl_m15_build_status_v2",
    "state": "running",
    "out_dir": os.path.abspath(OUTDIR),
    "force_refresh": FORCE_REFRESH,
    "requested_symbols": sorted(files_by_sym),
    "completed": [],
    "skipped": [],
    "failed": {},
}


def write_status():
    status["updated_epoch_s"] = time.time()
    tmp = STATUS_PATH + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(status, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, STATUS_PATH)


write_status()
for sym in sorted(files_by_sym):
    out = os.path.join(OUTDIR, f"{sym}.npz")
    if os.path.exists(out) and not FORCE_REFRESH:
        skipped += 1; status["skipped"].append(sym); write_status(); continue
    if time.time() - t0 > BUDGET:
        budget_exhausted = True
        print(f"[бюджет] остановился, осталось {len(files_by_sym)-done-skipped}"); break
    best = {}
    for fp in files_by_sym[sym]:
        df = None
        try:
            b = open(fp, "rb").read()
            head = b[:200].lstrip()
            if head.startswith(b"[[") or head.startswith(b'[["'):
                b2 = b.translate(None, b" \n\r\t").replace(b"],[", b"\n").translate(None, b"[]")
                df = pd.read_csv(io.BytesIO(b2), header=None, usecols=[0,1,2,3,4,5],
                                 names=["ts","o","h","l","c","v"], quotechar='"')
            else:
                # формат словарями: {"ts":..,"open":..} или {"start":..}
                raw = json.loads(b)
                if isinstance(raw, dict):
                    raw = raw.get("result", raw.get("list", raw.get("data", [])))
                    if isinstance(raw, dict): raw = raw.get("list", [])
                if not raw: raise ValueError("пусто")
                k = raw[0]
                if isinstance(k, list):
                    df = pd.DataFrame(raw).iloc[:, :6]
                    df.columns = ["ts","o","h","l","c","v"]
                else:
                    def pick(d, *names):
                        for nm in names:
                            if nm in d: return d[nm]
                        raise KeyError(names)
                    df = pd.DataFrame([{
                        "ts": pick(d,"ts","start","startTime","t","time","open_time"),
                        "o": pick(d,"o","open"), "h": pick(d,"h","high"),
                        "l": pick(d,"l","low"), "c": pick(d,"c","close"),
                        "v": pick(d,"v","volume","turnover")} for d in raw])
        except Exception as e:
            print(f"  {sym}: {os.path.basename(fp)} -> {type(e).__name__}: {e}"); continue
        if df is None or df.empty: continue
        df = df.astype({"ts":"int64","o":"float64","h":"float64","l":"float64",
                        "c":"float64","v":"float64"})
        # Bybit commonly returns newest -> oldest.  groupby(first/last) on an
        # unsorted page swaps the candle open and close while leaving high/low
        # plausible, which is a particularly dangerous silent corruption.
        df = df.sort_values("ts", kind="stable").drop_duplicates("ts", keep="last")
        df["b"] = df.ts // STEP * STEP
        g = df.groupby("b").agg(o=("o","first"), h=("h","max"), l=("l","min"),
                                c=("c","last"), v=("v","sum"), n=("ts","size"))
        if len(g) > 2: g = g.iloc[1:-1]          # края файла заведомо частичные
        for b, r in g.iterrows():
            prev = best.get(b)
            if prev is None or r["n"] > prev[5]:
                best[b] = (r["o"], r["h"], r["l"], r["c"], r["v"], r["n"])
        del df, g, b; gc.collect()
    if len(best) < MIN_BARS:
        print(f"  {sym}: мало баров ({len(best)})")
        status["failed"][sym] = f"too_few_bars:{len(best)}"
        done += 1; write_status(); continue
    ks = np.array(sorted(best))
    arr = np.array([best[k][:5] for k in ks], dtype=np.float32)
    nsub = np.array([best[k][5] for k in ks], dtype=np.int16)
    fd, tmp_out = tempfile.mkstemp(prefix=f".{sym}.", suffix=".npz.tmp", dir=OUTDIR)
    try:
        with os.fdopen(fd, "wb") as handle:
            np.savez_compressed(handle, ts=ks, ohlcv=arr, nsub=nsub)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_out, out)
    except Exception:
        try: os.unlink(tmp_out)
        except OSError: pass
        raise
    done += 1
    status["completed"].append(sym)
    write_status()
    print(f"  {sym}: {len(ks):,} баров  ({time.time()-t0:.0f} с)")
status["state"] = (
    "budget_exhausted" if budget_exhausted
    else "complete" if not status["failed"]
    else "complete_with_failures"
)
status["elapsed_seconds"] = round(time.time() - t0, 3)
write_status()
print(f"готово {done}, пропущено {skipped}, время {time.time()-t0:.0f} с")
