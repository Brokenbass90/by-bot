"""Диагностика потерь Structural V1 и v4+структурное ведение + версия V2 (частичная фиксация у следующего подтверждённого уровня).
Правила V2 заданы ДО прогона: вход — входы v4 (ретест, ровно сделки прогона ab_M_noBE); стоп — последний подтверждённый swing;
частичная фиксация 50 % (доля из исходного замысла v4, не подбиралась) за 0.1 ATR до ближайшего подтверждённого горизонтального
уровня по ходу сделки, известного на момент входа (horizontal_levels по 120 закрытым часам), если он дальше 0.5 риска от входа;
нет уровня → без частичной; остаток — структурный перенос, до 72 ч. Расходы 8 bps на сторону на каждую часть."""
import sys, csv, glob, json, math, random, statistics as st
sys.path.insert(0, '/root/struct'); sys.path.insert(0, '/root/devfix')
import structural_v1 as S
import bot.market_context as mc
H = S.H; FEE = 8e-4
syms = sorted(p.split('/')[-1].split('_5_')[0] for p in glob.glob('/root/irv4/.cache/klines/*_5_*.json'))
B = {s: S.chasy(s) for s in syms}; IDX = {s: {r[0]: i for i, r in enumerate(B[s])} for s in syms}

def put(b, i, side, entry, maxh=72):
    """MFE/MAE в единицах риска + путь структурного ведения; возвращает подробности."""
    s0 = S.swing(b, i - 1, side)
    if s0 is None: return None
    risk = (entry - s0) if side == 'long' else (s0 - entry)
    if risk <= 0: return None
    stop = s0; mfe = mae = 0.0; exit_px = None; k_exit = None
    for k in range(i, min(len(b), i + maxh)):
        hi, lo = b[k][2], b[k][3]
        fav = (hi - entry) if side == 'long' else (entry - lo); adv = (entry - lo) if side == 'long' else (hi - entry)
        if (side == 'long' and lo <= stop) or (side == 'short' and hi >= stop):
            mae = max(mae, min(adv, risk)); exit_px = stop; k_exit = k; break
        mfe = max(mfe, fav); mae = max(mae, adv)
        s2 = S.swing(b, k, side)
        if s2 is not None:
            if side == 'long' and stop < s2 < b[k][4]: stop = s2
            if side == 'short' and b[k][4] < s2 < stop: stop = s2
    if exit_px is None: k_exit = min(len(b) - 1, i + maxh); exit_px = b[k_exit][4]
    return dict(risk=risk, mfe=mfe / risk, mae=mae / risk, exit=exit_px, k_exit=k_exit, hold=k_exit - i)

def sled_uroven(b, i, side, entry, risk, a):
    okno = b[i - 121:i]
    lv = mc.horizontal_levels(okno, side='resistance' if side == 'long' else 'support', atr_value=a)
    L = [float(x['level']) for x in lv]
    L = [x for x in L if (x > entry + 0.5 * risk if side == 'long' else x < entry - 0.5 * risk)]
    if not L: return None
    return min(L) if side == 'long' else max(L)

def sdelka_v2(b, i, side, entry):
    a = mc.atr(b[i - 31:i], 14); p = put(b, i, side, entry)
    if p is None or not (a == a and a > 0) or p['risk'] > S.MAX_RISK_ATR * a: return None
    risk = p['risk']; L = sled_uroven(b, i, side, entry, risk, a)
    sgn = 1 if side == 'long' else -1
    r_full = sgn * (p['exit'] - entry) / risk - 2 * FEE * entry / risk
    if L is None:
        return dict(R=r_full, R_bez=r_full, uroven=False, dostig=False, **p)
    tp = L - 0.1 * a if side == 'long' else L + 0.1 * a
    dostig = False
    for k in range(i, p['k_exit'] + 1):        # дошла ли цена до цели раньше выхода (на баре выхода — стоп первым)
        if k == p['k_exit'] and p['hold'] < 72: break
        if (side == 'long' and b[k][2] >= tp) or (side == 'short' and b[k][3] <= tp): dostig = True; break
    if dostig:
        r = 0.5 * sgn * (tp - entry) / risk + 0.5 * sgn * (p['exit'] - entry) / risk - 3 * FEE * entry / risk  # вход + 2 выхода
    else:
        r = r_full
    return dict(R=r, R_bez=r_full, uroven=True, dostig=dostig, rasst_R=abs(L - entry) / risk, **p)

def vhody_v4():
    f = glob.glob('/root/irv4/backtest_runs/portfolio_*_ab_M_noBE/trades.csv')[0]; out = []
    for t in csv.DictReader(open(f)):
        b = B[t['symbol']]; i = IDX[t['symbol']].get(int(t['entry_ts']) // H * H)
        if i is None or i < 800 or i + 75 >= len(b): continue
        out.append((t['symbol'], i, t['side'], float(t['entry_price'])))
    return out

def vhody_v1():
    return [(x['sym'], x['i'] + 1, x['side'], B[x['sym']][x['i'] + 1][1]) for s in syms for x in S.signaly(s, B[s], False, False)]

def raspr(xs):
    xs = sorted(xs); q = lambda p: round(xs[int(p * (len(xs) - 1))], 2)
    return dict(p25=q(.25), med=q(.5), p75=q(.75))

def otchet(nm, vh):
    rows = [dict(sym=s, side=sd, **r) for s, i, sd, e in vh if (r := sdelka_v2(B[s], i, sd, e))]
    n = len(rows); R = [r['R'] for r in rows]; Rb = [r['R_bez'] for r in rows]
    S7 = S.S7
    def dd(v):
        eq = pk = m = 0
        for x in v: eq += x; pk = max(pk, eq); m = max(m, pk - eq)
        return round(m, 1)
    kom = st.mean(2 * FEE * 1 for _ in rows)
    o = dict(n=n,
             bez_fiksacii=dict(R=round(st.mean(Rb), 3), t=round(st.mean(Rb) / (st.stdev(Rb) / math.sqrt(n)), 2), itog=round(sum(Rb), 1), maxDD_R=dd(Rb)),
             V2_s_fiksaciey=dict(R=round(st.mean(R), 3), t=round(st.mean(R) / (st.stdev(R) / math.sqrt(n)), 2), itog=round(sum(R), 1), maxDD_R=dd(R),
                                 drugie9=round(sum(r['R'] for r in rows if r['sym'] not in S7), 1), drugie_n=sum(r['sym'] not in S7 for r in rows)),
             MFE_R=raspr([r['mfe'] for r in rows]), MAE_R=raspr([r['mae'] for r in rows]), uderzhanie_ch=raspr([r['hold'] for r in rows]),
             s_urovnem=sum(r['uroven'] for r in rows), doshli_do_urovnya=sum(r['dostig'] for r in rows),
             rasst_do_urovnya_R=raspr([r['rasst_R'] for r in rows if r['uroven']]) if any(r['uroven'] for r in rows) else None,
             doshli_1R=round(sum(r['mfe'] >= 1 for r in rows) / n, 2), doshli_2R=round(sum(r['mfe'] >= 2 for r in rows) / n, 2),
             rashody_R_na_sdelku=round(st.mean(2 * FEE * 1 / (r['risk'] / 1) * 0 for r in rows), 3))
    # расходы в R: 2 стороны × 8 bps × цена / риск
    o['rashody_R_na_sdelku'] = round(st.mean([2 * FEE * B[r['sym']][0][4] * 0 for r in rows]) if False else 0, 3)
    return o, rows

if __name__ == '__main__':
    rez = {}
    for nm, vh in (('v4_vhody', vhody_v4()), ('V1_vhody', vhody_v1())):
        o, rows = otchet(nm, vh)
        # доля расходов: средний R до расходов − после
        rez[nm] = o; print(nm, json.dumps(o, ensure_ascii=False), flush=True)
    json.dump(rez, open('/root/struct/v2_diag_20261021.json', 'w'), ensure_ascii=False, indent=1)
