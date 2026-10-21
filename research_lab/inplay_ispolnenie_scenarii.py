"""Сценарии исполнения для входов v4 + структурное ведение (193 сделки, без лимита риска). Входы, стопы, ведение не меняются.
Ставки: стандартный (не VIP) тариф Bybit USDT-перпетуалов maker 0.02 % / taker 0.055 % — проверить по аккаунту владельца.
Оптимистичный: вход maker, все лимиты исполнены; выход taker + 1 bps. Базовый: вход maker только если 5m-цена прошла лимит на
≥ 5 bps (иначе сделки нет), выход taker + 3 bps, фандинг 1 bps за каждые 8 ч удержания. Стрессовый: вход как taker + 2 bps
(лимит пересёк спред), выход taker + 5 bps, фандинг 1 bps / 8 ч."""
import sys, csv, glob, json, math, statistics as st
sys.path.insert(0,'/root/struct'); sys.path.insert(0,'/root/devfix')
import v2_diag as D
MK, TK = 2e-4, 5.5e-4
m5 = {}
def bar5(sym, ts):
    if sym not in m5:
        f = glob.glob(f'/root/irv4/.cache/klines/{sym}_5_*.json')[0]; d = json.load(open(f)); rows = d if isinstance(d, list) else d['records']
        m5[sym] = {int(r[0]): [float(x) for x in r[1:6]] for r in rows}
    return m5[sym].get(ts)
f = glob.glob('/root/irv4/backtest_runs/portfolio_*_ab_M_noBE/trades.csv')[0]
sdelki = []
for t in csv.DictReader(open(f)):
    s = t['symbol']; b = D.B[s]; i = D.IDX[s].get(int(t['entry_ts']) // D.H * D.H)
    if i is None or i < 800 or i + 75 >= len(b): continue
    e = float(t['entry_price']); p = D.put(b, i, t['side'], e)
    if p is None: continue
    sgn = 1 if t['side'] == 'long' else -1
    b5 = bar5(s, int(t['entry_ts']))
    proshla = b5 is not None and ((b5[2] <= e * (1 - 5e-4)) if sgn == 1 else (b5[1] >= e * (1 + 5e-4)))
    sdelki.append(dict(sym=s, gross=sgn * (p['exit'] - e) / p['risk'], k=e / p['risk'], hold=p['hold'], proshla=proshla))
def scen(vh_fee, vyh_fee, fund_8h, tolko_proshla):
    R = []
    for x in sdelki:
        if tolko_proshla and not x['proshla']: continue
        cost = (vh_fee + vyh_fee + fund_8h * math.ceil(x['hold'] / 8)) * x['k']
        R.append(x['gross'] - cost)
    m = st.mean(R); return dict(n=len(R), R=round(m, 3), t=round(m / (st.stdev(R) / math.sqrt(len(R))), 2), na_10usd=round(10 * m, 2), za_god_10usd=round(10 * m * len(R) / 9.1 * 12, 0))
rez = dict(
    vse_do_rashodov=dict(n=len(sdelki), R=round(st.mean(x['gross'] for x in sdelki), 3)),
    dolya_proshla_limit=round(sum(x['proshla'] for x in sdelki) / len(sdelki), 2),
    do_rashodov_tolko_proshedshie=round(st.mean(x['gross'] for x in sdelki if x['proshla']), 3),
    optimistichnyy=scen(MK, TK + 1e-4, 0, False),
    bazovyy=scen(MK, TK + 3e-4, 1e-4, True),
    stressovyy=scen(TK + 2e-4, TK + 5e-4, 1e-4, False),
    kak_v_DEV_8bps=scen(8e-4, 8e-4, 0, False),
    srednyaya_dolya_ceny_v_riske=round(st.mean(1 / x['k'] for x in sdelki) * 100, 2))
# безубыточная стоимость круга: при какой сумме bps на круг R = 0
g = st.mean(x['gross'] for x in sdelki); kk = st.mean(x['k'] for x in sdelki)
rez['bezubytochnyy_krug_bps'] = round(g / kk * 1e4, 1)
print(json.dumps(rez, ensure_ascii=False, indent=1)); json.dump(rez, open('/root/struct/ispolnenie_20261021.json', 'w'), ensure_ascii=False, indent=1)
