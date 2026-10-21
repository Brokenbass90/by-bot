import random, statistics as st, math, csv, glob
exec(open('forensika.py').read().split("S7 = {")[0])
random.seed(7)
tr = list(csv.DictReader(open(glob.glob('/root/irv4/backtest_runs/portfolio_*_ab_M_noBE/trades.csv')[0])))
syms = sorted({t['symbol'] for t in tr}); B = {s: chasy(s) for s in syms}
real, ctrl = [], []
for t in tr:
    ts, b = B[t['symbol']]; idx = {x: i for i, x in enumerate(ts)}
    i = idx.get(int(t['entry_ts']) // H * H)
    if i is None or i < 60 or i + 73 >= len(b): continue
    r = struktur_vedenie(b, i, t['side'], float(t['entry_price']))
    if not r: continue
    real.append(r['R'])
    for _ in range(5):   # случайный вход той же монеты и стороны в пределах ±30 дней, по открытию часа
        k = random.randint(max(60, i - 720), min(len(b) - 74, i + 720))
        c = struktur_vedenie(b, k, t['side'], b[k][0])
        if c: ctrl.append(c['R'])
def s(x): return f"n={len(x)} сред={st.mean(x):+.3f} t={st.mean(x)/(st.stdev(x)/math.sqrt(len(x))):+.2f}"
print('вход v4 + структурное ведение', s(real)); print('случайный вход + то же ведение', s(ctrl))
