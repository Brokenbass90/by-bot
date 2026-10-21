"""Замеры VYNOS_NAKLONNOY по prereg d698d57. Без доходностей."""
import sys, json, math, random, statistics as st, collections
sys.path.insert(0, '/root/struct'); sys.path.insert(0, '/root/devfix')
import structural_v1 as S
import bot.market_context as mc
random.seed(20261021)
syms = sorted(p.split('/')[-1].split('_5_')[0] for p in __import__('glob').glob('/root/irv4/.cache/klines/*_5_*.json'))
B = {s: S.chasy(s) for s in syms}
def linia(b, i, side):
    okno = b[i - 120:i]                     # бары до i−1 включительно
    sl = mc.sloped_level(okno, side=side, left=2, right=2, min_pivots=2, last_pivots=3)
    if sl is None or not sl['valid']: return None
    return sl['level_now'] + sl['slope']    # продление на бар i
def gonka(b, j, side, stop, risk, maxh=48):
    e = b[j][1]; tgt = e - 1.5 * risk if side == 'short' else e + 1.5 * risk
    for k in range(j, min(len(b), j + maxh)):
        if side == 'short':
            if b[k][2] >= stop: return 0
            if b[k][3] <= tgt: return 1
        else:
            if b[k][3] <= stop: return 0
            if b[k][2] >= tgt: return 1
    return None
ev = []
for s in syms:
    b = B[s]; last = {}
    for i in range(130, len(b) - 50):
        if not (S.T0 <= b[i][0] <= S.T1): continue
        a = mc.atr(b[i - 30:i], 14)
        if not (a == a and a > 0): continue
        for side, lside in (('short', 'resistance'), ('long', 'support')):
            if b[i][0] - last.get(side, -10**15) < 12 * S.H: continue
            L = linia(b, i, lside)
            if L is None: continue
            if side == 'short' and b[i][2] > L + 0.1 * a and b[i][4] < L: ext = b[i][2] + 0.1 * a
            elif side == 'long' and b[i][3] < L - 0.1 * a and b[i][4] > L: ext = b[i][3] - 0.1 * a
            else: continue
            last[side] = b[i][0]
            e = b[i + 1][1]; risk = (ext - e) if side == 'short' else (e - ext)
            if risk <= 0: continue
            uderzh = all((b[k][4] < L) if side == 'short' else (b[k][4] > L) for k in range(i + 1, i + 4))
            w = gonka(b, i + 1, side, ext, risk)
            # контроль: случайный час той же монеты/стороны ±30 дн, тот же стоп в ATR
            ra = risk / a; ctrl = []
            for _ in range(5):
                k = random.randint(max(130, i - 720), min(len(b) - 50, i + 720)); ak = mc.atr(b[k - 30:k], 14)
                if not (ak == ak and ak > 0): continue
                ek = b[k + 1][1]; rk = ra * ak; st_ = ek + rk if side == 'short' else ek - rk
                c = gonka(b, k + 1, side, st_, rk)
                if c is not None: ctrl.append(c)
            ev.append(dict(sym=s, ts=b[i][0], side=side, uderzh=uderzh, win=w, ctrl=st.mean(ctrl) if ctrl else None,
                           nedelya=b[i][0] // (7 * 86400000), s7=s in S.S7))
ok = [x for x in ev if x['win'] is not None and x['ctrl'] is not None]
def klaster_t(xs, key):
    g = collections.defaultdict(list)
    for x in xs: g[x['nedelya']].append(x['win'] - x['ctrl'])
    m = [sum(v) for v in g.values()]; n = len(xs)
    mean = sum(m) / n; se = math.sqrt(sum((v - mean * len(g[w])) ** 2 for v, w in zip(m, g)) ) / n if n else 0
    return round(mean, 3), round(mean / se, 2) if se > 0 else None
def blok(xs):
    if len(xs) < 10: return dict(n=len(xs))
    d, t = klaster_t(xs, None)
    return dict(n=len(xs), dolya_pobed=round(st.mean(x['win'] for x in xs), 3), etalon=0.4, kontrol=round(st.mean(x['ctrl'] for x in xs), 3),
                prevyshenie_nad_kontrolem=d, t_klaster_nedeli=t)
nedeli = collections.Counter(x['nedelya'] for x in ev); chasy = collections.Counter(x['ts'] for x in ev)
rez = dict(
    Z1=dict(sobytiy=len(ev), nedel_s_sobytiyami=len(nedeli), v_nedelyu_mediana=sorted(nedeli.values())[len(nedeli) // 2],
            dolya_sobytiy_v_obshchiy_chas_s_drugoy_monetoy=round(sum(v for v in chasy.values() if v > 1) / len(ev), 3)),
    Z2=dict(uderzhanie_3_zakrytiya=round(st.mean(x['uderzh'] for x in ev), 3)),
    Z3=dict(vse=blok(ok), shorty=blok([x for x in ok if x['side'] == 'short']), longi=blok([x for x in ok if x['side'] == 'long']),
            S7=blok([x for x in ok if x['s7']]), drugie9=blok([x for x in ok if not x['s7']]),
            uderzhali=blok([x for x in ok if x['uderzh']]), ne_uderzhali=blok([x for x in ok if not x['uderzh']])))
print(json.dumps(rez, ensure_ascii=False, indent=1)); json.dump(rez, open('/root/struct/vynos_naklonnoy_20261021.json', 'w'), ensure_ascii=False, indent=1)
