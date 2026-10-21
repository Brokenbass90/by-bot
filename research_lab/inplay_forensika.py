"""Trade forensics InPlay (21.10.2026): правило выборки до просмотра — 10 прибыльных, 10 убыточных (вариант M_noBE),
10 пропущенных движений; random.seed(20261021). Плюс сводные признаки по ВСЕМ сделкам. Только данные, известные до решения."""
import csv, glob, json, random, statistics as st, math
H = 3_600_000; random.seed(20261021)
CACHE = '/root/irv4/.cache/klines'
def chasy(sym):
    f = glob.glob(f'{CACHE}/{sym}_5_*.json')[0]; d = json.load(open(f)); rows = d if isinstance(d, list) else d['records']
    m = {}
    for r in rows:
        t = int(r[0]) // H * H; o, h, l, c, v = map(float, r[1:6])
        x = m.get(t)
        if x is None: m[t] = [o, h, l, c, v]
        else: x[1] = max(x[1], h); x[2] = min(x[2], l); x[3] = c; x[4] += v
    ts = sorted(m); return ts, [m[t] for t in ts]
def atr(b, i, n=14):
    return sum(max(b[k][1]-b[k][2], abs(b[k][1]-b[k-1][3]), abs(b[k][2]-b[k-1][3])) for k in range(i-n, i)) / n
def swing_low(b, i, L=2, R=2):   # последний подтверждённый минимум, известный к бару i (подтверждение через R баров)
    for k in range(i-R-1, L, -1):
        if all(b[k][2] <= b[k+j][2] for j in range(-L, R+1) if j): return k, b[k][2]
    return None, None
def swing_high(b, i, L=2, R=2):
    for k in range(i-R-1, L, -1):
        if all(b[k][1] >= b[k+j][1] for j in range(-L, R+1) if j): return k, b[k][1]
    return None, None
def struktur_vedenie(b, i, side, entry, maxh=72):
    """Стоп за последним подтверждённым swing до входа; перенос только за новый подтверждённый swing (известен с задержкой R=2)."""
    if side == 'long':
        _, s = swing_low(b, i)
    else:
        _, s = swing_high(b, i)
    if s is None: return None
    risk = (entry - s) if side == 'long' else (s - entry)
    if risk <= 0: return None
    stop = s
    for k in range(i, min(len(b), i + maxh)):
        lo, hi = b[k][2], b[k][1]
        if side == 'long' and lo <= stop: return dict(R=(stop-entry)/risk, bars=k-i, risk_atr=risk)
        if side == 'short' and hi >= stop: return dict(R=(entry-stop)/risk, bars=k-i, risk_atr=risk)
        if k >= i + 3:   # новый swing, подтверждённый к закрытию бара k
            if side == 'long':
                _, s2 = swing_low(b, k + 1)
                if s2 and s2 > stop and s2 < b[k][3]: stop = s2
            else:
                _, s2 = swing_high(b, k + 1)
                if s2 and s2 < stop and s2 > b[k][3]: stop = s2
    c = b[min(len(b)-1, i+maxh)][3]
    return dict(R=((c-entry) if side=='long' else (entry-c))/risk, bars=maxh, risk_atr=risk)
S7 = {'ADAUSDT','DOGEUSDT','SUIUSDT','DOTUSDT','LTCUSDT','LINKUSDT','SOLUSDT'}
tr = list(csv.DictReader(open(glob.glob('/root/irv4/backtest_runs/portfolio_*_ab_M_noBE/trades.csv')[0])))
syms = sorted({t['symbol'] for t in tr}); B = {s: chasy(s) for s in syms}
rows = []
for t in tr:
    ts, b = B[t['symbol']]; idx = {x: i for i, x in enumerate(ts)}
    t0 = int(t['entry_ts']) // H * H; i = idx.get(t0)
    if i is None or i < 60 or i + 73 >= len(b): continue
    a = atr(b, i); e = float(t['entry_price']); sd = 1 if t['side'] == 'long' else -1
    hi48 = max(x[1] for x in b[i-48:i]); lo48 = min(x[2] for x in b[i-48:i])
    v20 = st.mean(x[4] for x in b[i-21:i-1]) or 1
    # нога отката: от экстремума последних 12 баров до входа
    if sd == 1: k_ext = max(range(i-12, i), key=lambda k: b[k][1])
    else: k_ext = min(range(i-12, i), key=lambda k: b[k][2])
    noga = b[k_ext+1:i] or [b[i-1]]
    v_noga = st.mean(x[4] for x in noga) / v20
    v_bar = b[i-1][4] / v20
    mfe = max(sd*(x[1 if sd==1 else 2]-e) for x in b[i:i+24]) / a
    mae = max(-sd*(x[2 if sd==1 else 1]-e) for x in b[i:i+24]) / a
    sv = struktur_vedenie(b, i, t['side'], e)
    rows.append(dict(sym=t['symbol'], side=t['side'], ts=t['entry_ts'], pnl=float(t['pnl']), reason=t['reason'][:40],
                     setup=t['reason'][:6], s7=t['symbol'] in S7, szhatie=(hi48-lo48)/a, v_noga=v_noga, v_bar=v_bar,
                     mfe=mfe, mae=mae, hold_h=(int(t['exit_ts'])-int(t['entry_ts']))/H,
                     sv_R=sv['R'] if sv else None, sv_bars=sv['bars'] if sv else None, sv_risk_atr=sv['risk_atr']/a if sv else None))
def m(xs): xs=[x for x in xs if x is not None]; return round(st.mean(xs),3) if xs else None
out = {}
win = [r for r in rows if r['pnl'] > 0]; los = [r for r in rows if r['pnl'] <= 0]
for nm, g in (('vse', rows), ('pribylnye', win), ('ubytochnye', los)):
    out[nm] = dict(n=len(g), szhatie=m(r['szhatie'] for r in g), v_noga=m(r['v_noga'] for r in g), v_bar=m(r['v_bar'] for r in g),
                   mfe24_atr=m(r['mfe'] for r in g), mae24_atr=m(r['mae'] for r in g), hold_h=m(r['hold_h'] for r in g),
                   sv_R=m(r['sv_R'] for r in g), sv_risk_atr=m(r['sv_risk_atr'] for r in g))
sv = [r['sv_R'] for r in rows if r['sv_R'] is not None]
out['strukturnoe_vedenie_vse'] = dict(n=len(sv), sred_R=round(st.mean(sv),3), t=round(st.mean(sv)/(st.stdev(sv)/math.sqrt(len(sv))),2),
    S7=m(r['sv_R'] for r in rows if r['s7']), drugie=m(r['sv_R'] for r in rows if not r['s7']))
vybor = random.sample(win, 10) + random.sample(los, 10)
# пропущенные движения: |close[t+24]-close[t]| >= 4 ATR, нет сделки по монете в ±24ч, по одному на монету за 48ч
tset = {}
for t in tr: tset.setdefault(t['symbol'], []).append(int(t['entry_ts']))
miss = []
for s in syms:
    ts, b = B[s]; last = -10**15
    for i in range(60, len(b)-25):
        if ts[i] < 1750550400000 or ts[i] > 1774310400000: continue
        a = atr(b, i); mv = (b[i+24][3]-b[i][0]) / a
        if abs(mv) >= 4 and ts[i]-last > 48*H and not any(abs(x-ts[i]) <= 24*H for x in tset.get(s, [])):
            hi48 = max(x[1] for x in b[i-48:i]); lo48 = min(x[2] for x in b[i-48:i]); v20 = st.mean(x[4] for x in b[i-21:i-1]) or 1
            miss.append(dict(sym=s, ts=ts[i], dvizhenie_atr=round(mv,1), szhatie=round((hi48-lo48)/a,1),
                             v_pervyy_chas=round(b[i][4]/v20,2), proboy_48=bool(b[i+3][3] > hi48 or b[i+3][3] < lo48)))
            last = ts[i]
out['propushcheno_vsego'] = len(miss)
out['propushcheno_svod'] = dict(szhatie=m(x['szhatie'] for x in miss), v_pervyy_chas=m(x['v_pervyy_chas'] for x in miss),
                                dolya_proboy48=round(sum(x['proboy_48'] for x in miss)/max(1,len(miss)),2))
out['vyborka_sdelki'] = vybor; out['vyborka_propushcheno'] = random.sample(miss, min(10, len(miss)))
json.dump(out, open('/root/forens/forensika_20261021.json','w'), ensure_ascii=False, indent=1, default=str)
for k in ('vse','pribylnye','ubytochnye','strukturnoe_vedenie_vse','propushcheno_vsego','propushcheno_svod'): print(k, out[k])
for r in vybor: print(r['sym'], r['side'], r['setup'], f"pnl={r['pnl']:+.2f} сжатие={r['szhatie']:.1f} vноги={r['v_noga']:.2f} vбара={r['v_bar']:.2f} MFE={r['mfe']:.1f} MAE={r['mae']:.1f} удерж={r['hold_h']:.1f}ч струкR={r['sv_R']}")
for x in out['vyborka_propushcheno']: print('ПРОПУСК', x)
