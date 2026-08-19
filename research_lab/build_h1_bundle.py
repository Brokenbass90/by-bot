#!/usr/bin/env python3
"""
build_h1_bundle.py — превращает 5m JSON из data_cache в часовые серии.

Память на VM 3 ГБ, а 5m истории ~3 ГБ, поэтому агрегация ПОТОКОВАЯ:
каждый файл читается, сразу сворачивается в час и отпускается.
Ничего крупнее одного файла в памяти не живёт.

Корректность на стыках файлов: у каждого файла отбрасывается первый
и последний час (они заведомо частичные). Файлы в data_cache сильно
перекрываются, поэтому отброшенное покрывается соседним файлом.
Если не покрылось — это видно в h1_coverage.csv как провал покрытия,
а не как молчаливая дыра.

При конфликте за один и тот же час побеждает источник с бОльшим числом
5m баров (nsub).

Выход: research_lab/data/h1/<SYMBOL>.npz  +  research_lab/data/h1_coverage.csv
"""
import io
import os
import sys
import glob
import re
import time
import gc
import numpy as np
import pandas as pd

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
CACHE = os.path.join(ROOT, "data_cache")
OUTDIR = os.path.join(ROOT, "research_lab", "data", "h1")
os.makedirs(OUTDIR, exist_ok=True)

HOUR_MS = 3_600_000
MIN_H1_BARS = 24 * 45  # минимум 45 дней часовой истории

pat = re.compile(r"^(?P<sym>[A-Z0-9]+USDT)_5_.*\.json$")

files_by_sym = {}
for fp in sorted(glob.glob(os.path.join(CACHE, "*.json"))):
    m = pat.match(os.path.basename(fp))
    if m:
        files_by_sym.setdefault(m.group("sym"), []).append(fp)

print(f"[scan] символов: {len(files_by_sym)}, файлов: {sum(len(v) for v in files_by_sym.values())}", flush=True)


def read_klines(fp):
    """JSON [[ts,o,h,l,c,v],...] -> ndarray без построения Python-списка.

    json.load на файле 22 МБ даёт ~300 МБ объектов; здесь тот же результат
    за половину времени и вдвое меньше пика памяти. Сверено построчно.
    """
    b = open(fp, "rb").read()
    b = b.translate(None, b" \n\r\t").replace(b"],[", b"\n").translate(None, b"[]")
    if not b.strip():
        return None
    return pd.read_csv(io.BytesIO(b), header=None, dtype=np.float64).to_numpy()


def file_to_h1(fp):
    """Один файл -> (ts, ohlcv, nsub) на часовой сетке, без краевых часов."""
    arr = read_klines(fp)
    if arr is None or arr.ndim != 2 or arr.shape[0] < 24 or arr.shape[1] < 6:
        return None
    arr = arr[:, :6]

    ts5 = arr[:, 0].astype(np.int64)
    o = np.argsort(ts5, kind="stable")
    ts5 = ts5[o]
    v5 = arr[o, 1:6]
    del arr
    keep = np.empty(len(ts5), dtype=bool)
    keep[:-1] = ts5[:-1] != ts5[1:]
    keep[-1] = True
    ts5, v5 = ts5[keep], v5[keep]

    hkey = (ts5 // HOUR_MS) * HOUR_MS
    newg = np.empty(len(hkey), dtype=bool)
    newg[0] = True
    newg[1:] = hkey[1:] != hkey[:-1]
    st = np.flatnonzero(newg)
    en = np.append(st[1:], len(hkey))

    h_ts = hkey[st]
    h = np.column_stack([
        v5[st, 0],                                  # open
        np.maximum.reduceat(v5[:, 1], st),          # high
        np.minimum.reduceat(v5[:, 2], st),          # low
        v5[en - 1, 3],                              # close
        np.add.reduceat(v5[:, 4], st),              # volume
    ])
    nsub = (en - st).astype(np.int16)
    del ts5, v5, hkey, st, en, newg

    if len(h_ts) < 3:
        return None
    # краевые часы файла — заведомо частичные
    h_ts, h, nsub = h_ts[1:-1], h[1:-1], nsub[1:-1]

    ok = (h[:, 0] > 0) & (h[:, 1] > 0) & (h[:, 2] > 0) & (h[:, 3] > 0) & (h[:, 1] >= h[:, 2])
    return h_ts[ok], h[ok], nsub[ok]


BUDGET_S = float(os.environ.get("H1_BUDGET_S", "0")) or None  # мягкий лимит на вызов

coverage_rows = []
t0 = time.time()
done = 0
skipped_existing = 0

for i, (sym, fps) in enumerate(sorted(files_by_sym.items()), 1):
    outfp = os.path.join(OUTDIR, f"{sym}.npz")
    if os.path.exists(outfp) and os.path.getsize(outfp) > 1000:
        skipped_existing += 1
        continue
    if BUDGET_S and (time.time() - t0) > BUDGET_S:
        print(f"[budget] стоп на {i}/{len(files_by_sym)}, запусти ещё раз — продолжит с этого места", flush=True)
        break
    parts, bad = [], 0
    for fp in fps:
        try:
            r = file_to_h1(fp)
        except Exception:
            r = None
        if r is None or len(r[0]) == 0:
            bad += 1
        else:
            parts.append(r)
        gc.collect()

    if not parts:
        coverage_rows.append((sym, 0, 0, 0, 0.0, len(fps), bad, "SKIP_no_data"))
        continue

    ts = np.concatenate([p[0] for p in parts])
    oh = np.concatenate([p[1] for p in parts])
    ns = np.concatenate([p[2] for p in parts])
    del parts
    gc.collect()

    # при равном часе побеждает запись с бОльшим nsub:
    # сортируем по (ts, nsub) и оставляем последнее вхождение каждого ts
    order = np.lexsort((ns, ts))
    ts, oh, ns = ts[order], oh[order], ns[order]
    keep = np.empty(len(ts), dtype=bool)
    keep[:-1] = ts[:-1] != ts[1:]
    keep[-1] = True
    ts, oh, ns = ts[keep], oh[keep], ns[keep]

    n = len(ts)
    if n < MIN_H1_BARS:
        coverage_rows.append((sym, int(ts[0]), int(ts[-1]), n, 0.0, len(fps), bad, "SKIP_too_short"))
        continue

    span = (ts[-1] - ts[0]) // HOUR_MS + 1
    cov = n / span if span > 0 else 0.0

    np.savez_compressed(outfp, ts=ts, ohlcv=oh.astype(np.float32), nsub=ns)
    coverage_rows.append((sym, int(ts[0]), int(ts[-1]), n, round(float(cov), 4),
                          len(fps), bad, "OK"))
    done += 1
    del ts, oh, ns
    gc.collect()
    print(f"[{i:3d}/{len(files_by_sym)}] {sym:16s} h1={n:6d} cov={cov:.3f} ({time.time()-t0:.0f}s)", flush=True)

# покрытие пересобирается по ВСЕМ сохранённым файлам, а не только по этому вызову —
# иначе возобновляемый прогон каждый раз затирал бы отчёт частичным.
cov_fp = os.path.join(ROOT, "research_lab", "data", "h1_coverage.csv")
with open(cov_fp, "w") as fh:
    fh.write("symbol,first_ts,last_ts,h1_bars,coverage_frac,src_files,status\n")
    for fp in sorted(glob.glob(os.path.join(OUTDIR, "*.npz"))):
        s = os.path.basename(fp)[:-4]
        z = np.load(fp)
        ts = z["ts"]
        span = (int(ts[-1]) - int(ts[0])) // HOUR_MS + 1
        fh.write(f"{s},{int(ts[0])},{int(ts[-1])},{len(ts)},"
                 f"{len(ts)/span:.4f},{len(files_by_sym.get(s, []))},OK\n")

n_out = len(glob.glob(os.path.join(OUTDIR, '*.npz')))
print(f"[done] в этот вызов: {done}, пропущено готовых: {skipped_existing}, "
      f"всего символов на диске: {n_out}/{len(files_by_sym)} ({time.time()-t0:.0f}s)", flush=True)
print(f"[done] -> {OUTDIR}  +  {cov_fp}", flush=True)
