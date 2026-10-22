#!/usr/bin/env python3
"""TREND_TREYL_D1 — prereg PREREG_TREND_TREYL_D1_2026_10_22 (9b76633). Попытка реестра TREND_TREYL_D1_V1_A1."""
import glob, json, math, random, statistics as st, datetime as dt, collections
from pathlib import Path
LAB = Path(__file__).resolve().parent
D = 86_400_000; T0 = int(dt.datetime(2021, 7, 1, tzinfo=dt.timezone.utc).timestamp() * 1000); T1 = int(dt.datetime(2022, 12, 31, tzinfo=dt.timezone.utc).timestamp() * 1000)
N, K, AP, MAXD = 55, 3.0, 20, 120
FEE, FUND_DAY = 8e-4, 3e-4
def atr(b, i):
    return sum(max(b[k][2] - b[k][3], abs(b[k][2] - b[k - 1][4]), abs(b[k][3] - b[k - 1][4])) for k in range(i - AP + 1, i + 1)) / AP
def sdelka(b, i, side, fixed=None):
    """решение по закрытию дня i; вход по открытию i+1; стоп/трейл по закрытию, выход по открытию следующего дня."""
    if i + 2 >= len(b): return None
    a = atr(b, i); e = b[i + 1][1]
    if not (a > 0): return None
    risk = K * a; best = e; sgn = 1 if side == 'long' else -1
    stop = e - sgn * risk
    for j in range(i + 1, min(len(b) - 1, i + 1 + MAXD)):
        c = b[j][4]
        if fixed is None:
            if (c <= stop) if sgn == 1 else (c >= stop):
                x = b[j + 1][1]; dni = j + 1 - (i + 1); break
            best = max(best, c) if sgn == 1 else min(best, c)
            a_j = atr(b, j); stop = max(stop, best - K * a_j) if sgn == 1 else min(stop, best + K * a_j)
        elif j - (i + 1) + 1 >= fixed:
            x = b[j + 1][1]; dni = j + 1 - (i + 1); break
    else:
        j = min(len(b) - 1, i + 1 + MAXD); x = b[j][4]; dni = j - (i + 1)
    R = sgn * (x - e) / risk - (2 * FEE * e + FUND_DAY * max(dni, 1) * e) / risk
    return dict(R=R, dni=dni, vyhod_idx=i + 1 + dni)
def main():
    random.seed(20261022); sd = []; ctrl_all = []
    for f in sorted(glob.glob(str(LAB / 'data/binance_kity/klines/*.json'))):
        b = json.load(open(f)); sym = Path(f).stem
        if len(b) < 200: continue
        okno = [i for i in range(max(120, N + AP), len(b) - 2) if T0 <= b[i][0] <= T1]
        i_free = 0
        for i in okno:
            if i < i_free or i - 120 < 0: continue
            hi = max(x[4] for x in b[i - N:i]); lo = min(x[4] for x in b[i - N:i]); c = b[i][4]
            side = 'long' if c > hi else ('short' if c < lo else None)
            if side is None: continue
            r = sdelka(b, i, side)
            if r is None: continue
            r30 = sdelka(b, i, side, fixed=30)
            ctrl = []
            for _ in range(5):
                k = random.choice(okno); rc = sdelka(b, k, side)
                if rc: ctrl.append(rc['R'])
            sd.append(dict(sym=sym, ts=b[i][0], side=side, R=r['R'], dni=r['dni'], R30=r30['R'] if r30 else None, ctrl=st.mean(ctrl) if ctrl else None))
            i_free = r['vyhod_idx'] + 1
    ok = [x for x in sd if x['ctrl'] is not None]
    def kt(xs, key):
        g = collections.defaultdict(list)
        for x in xs: g[x['ts'] // (7 * D)].append(key(x))
        n = len(xs); m = sum(sum(v) for v in g.values()) / n
        se = math.sqrt(sum((sum(v) - m * len(v)) ** 2 for v in g.values())) / n
        return round(m, 3), round(m / se, 2) if se else None
    def blok(xs):
        if len(xs) < 5: return dict(n=len(xs))
        R = [x['R'] for x in xs]; mR, tR = kt(xs, lambda x: x['R']); md, td = kt(xs, lambda x: x['R'] - x['ctrl'])
        return dict(n=len(xs), R=round(st.mean(R), 3), t_R=tR, kontrol=round(st.mean(x['ctrl'] for x in xs), 3), prevyshenie=md, t_prev=td,
                    R_fiks30=round(st.mean(x['R30'] for x in xs if x['R30'] is not None), 3), dolya_plus=round(sum(r > 0 for r in R) / len(R), 2),
                    med_dni=sorted(x['dni'] for x in xs)[len(xs) // 2], top10_dolya_itoga=round(sum(sorted(R)[-max(1, len(R) // 10):]) / sum(R), 2) if sum(R) > 0 else None,
                    itog_R=round(sum(R), 1))
    rez = dict(vse=blok(ok), longi=blok([x for x in ok if x['side'] == 'long']), shorty=blok([x for x in ok if x['side'] == 'short']),
               po_godam={y: blok([x for x in ok if dt.datetime.utcfromtimestamp(x['ts'] / 1000).year == y]) for y in (2021, 2022)})
    (LAB / 'results' / 'trend_treyl_d1_20261022.json').write_text(json.dumps(dict(svod=rez, sdelki=ok), ensure_ascii=False, indent=0))
    print(json.dumps(rez, ensure_ascii=False, indent=1))
if __name__ == '__main__': main()
