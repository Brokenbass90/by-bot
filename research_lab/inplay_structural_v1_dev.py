"""InPlay Structural V1 — DEV-прототип (21.10.2026). Все правила заданы ДО прогона (не подбирались по результату).
Часовые бары (из 5m-кэша), решение по закрытому бару i, вход по открытию бара i+1, стоп раньше цели внутри бара.
Цепочка: сканер «в игре» → уровень пробит в сторону движения → откат к уровню на слабом объёме → отбой с объёмом →
стоп за подтверждённым swing → перенос только за новый подтверждённый swing, без безубытка, максимум 72 ч.
Варианты: наклонная (через 3 последние подтверждённые точки) как дополнительный уровень OFF/ON; Brain (строгий флэт → нет
продолжения) OFF/ON. Расходы 6+2 bps на сторону. Контроль: случайный вход той же монеты и стороны ±30 дн + то же ведение."""
import sys, glob, json, math, random, statistics as st
sys.path.insert(0, '/root/devfix')
import bot.market_context as mc
from bot.range_filter import range_state
H = 3_600_000; COST = 2 * 8e-4
S7 = {'ADAUSDT','DOGEUSDT','SUIUSDT','DOTUSDT','LTCUSDT','LINKUSDT','SOLUSDT'}
T0, T1 = 1750550400000, 1774310400000          # 22.06.2025 — 24.03.2026 (то же окно, что ablation)
# --- правила (фиксированы) ---
VOL_IN_PLAY, MOVE_ATR = 1.5, 2.0                # сканер: объём 24ч ≥ 1.5× медианы суток за 30 дн и |ход 24ч| ≥ 2 ATR
BREAK_WINDOW, BAND_ATR = 24, 0.5                 # уровень пробит за последние 24 ч; откат к уровню ± 0.5 ATR
MAX_RISK_ATR, MAX_HOLD = 3.0, 72

def chasy(sym):
    f = glob.glob(f'/root/irv4/.cache/klines/{sym}_5_*.json')[0]; d = json.load(open(f)); rows = d if isinstance(d, list) else d['records']
    m = {}
    for r in rows:
        t = int(r[0]) // H * H; o, h, l, c, v = map(float, r[1:6]); x = m.get(t)
        if x is None: m[t] = [t, o, h, l, c, v]
        else: x[2] = max(x[2], h); x[3] = min(x[3], l); x[4] = c; x[5] += v
    return [m[t] for t in sorted(m)]

def swing(b, i, side):   # последний подтверждённый (2/2) экстремум, известный к закрытию бара i
    for k in range(i - 2, 2, -1):
        if side == 'long' and all(b[k][3] <= b[k + j][3] for j in (-2, -1, 1, 2)): return b[k][3]
        if side == 'short' and all(b[k][2] >= b[k + j][2] for j in (-2, -1, 1, 2)): return b[k][2]
    return None

def vedenie(b, i, side, entry):
    s = swing(b, i - 1, side)
    if s is None: return None
    risk = (entry - s) if side == 'long' else (s - entry)
    if risk <= 0: return None
    stop = s
    for k in range(i, min(len(b), i + MAX_HOLD)):
        if side == 'long' and b[k][3] <= stop: return (stop - entry) / risk - COST * entry / risk, k - i, risk
        if side == 'short' and b[k][2] >= stop: return (entry - stop) / risk - COST * entry / risk, k - i, risk
        s2 = swing(b, k, side)
        if s2 is not None:
            if side == 'long' and stop < s2 < b[k][4]: stop = s2
            if side == 'short' and b[k][4] < s2 < stop: stop = s2
    c = b[min(len(b) - 1, i + MAX_HOLD)][4]
    return ((c - entry) if side == 'long' else (entry - c)) / risk - COST * entry / risk, MAX_HOLD, risk

def signaly(sym, b, naklonnaya, brain):
    out, poslednij = [], -10**9
    for i in range(760, len(b) - MAX_HOLD - 2):
        if not (T0 <= b[i][0] <= T1) or i - poslednij < 12: continue
        a = mc.atr(b[i - 30:i + 1], 14, exclude_last=False) if False else mc.atr(b[i - 30:i + 1], 14)
        if not (a == a and a > 0): continue
        v24 = sum(x[5] for x in b[i - 23:i + 1]); dn = sorted(sum(x[5] for x in b[k - 23:k + 1]) for k in range(i - 720, i, 24))
        if dn[len(dn) // 2] <= 0 or v24 < VOL_IN_PLAY * dn[len(dn) // 2]: continue          # не «в игре»
        mv = (b[i][4] - b[i - 24][4]) / a
        if abs(mv) < MOVE_ATR: continue
        side = 'long' if mv > 0 else 'short'
        okno = b[i - 120:i - BREAK_WINDOW + 1]                                               # уровни, существовавшие ДО пробоя
        lv = mc.horizontal_levels(okno, side='resistance' if side == 'long' else 'support', atr_value=a)
        urovni = [float(x['level']) for x in lv]
        if naklonnaya:
            sl = mc.sloped_level(okno, side='resistance' if side == 'long' else 'support', left=2, right=2, min_pivots=2, last_pivots=3)
            if sl is not None and sl['valid']:
                urovni.append(sl['level_now'] + sl['slope'] * BREAK_WINDOW)                   # линия, продлённая до текущего бара
        seg = b[i - BREAK_WINDOW:i]
        if side == 'long': urovni = [L for L in urovni if b[i - BREAK_WINDOW][4] < L and max(x[4] for x in seg) > L + 0.3 * a]
        else: urovni = [L for L in urovni if b[i - BREAK_WINDOW][4] > L and min(x[4] for x in seg) < L - 0.3 * a]
        if not urovni: continue
        L = max(urovni) if side == 'long' else min(urovni)
        bar = b[i]
        if side == 'long' and not (bar[3] <= L + BAND_ATR * a and bar[4] > L and bar[4] > bar[1]): continue
        if side == 'short' and not (bar[2] >= L - BAND_ATR * a and bar[4] < L and bar[4] < bar[1]): continue
        k_ext = max(range(i - BREAK_WINDOW, i), key=lambda k: b[k][2]) if side == 'long' else min(range(i - BREAK_WINDOW, i), key=lambda k: b[k][3])
        impuls = b[i - BREAK_WINDOW:k_ext + 1]; otkat = b[k_ext + 1:i]
        if not otkat or not impuls: continue
        if st.mean(x[5] for x in otkat) >= st.mean(x[5] for x in impuls): continue            # откат НЕ слабый
        v20 = st.mean(x[5] for x in b[i - 20:i])
        if bar[5] < v20: continue                                                           # отбой без объёма
        if brain:
            rs = range_state(b[i - 120:i + 1], allow_sloped=False)
            if rs.ok and rs.extra.get('is_flat_range'): continue                            # строгий флэт — продолжения не ждём
        entry = b[i + 1][1]; r = vedenie(b, i + 1, side, entry)
        if r is None or r[2] > MAX_RISK_ATR * a: continue
        out.append(dict(sym=sym, ts=b[i][0], side=side, R=r[0], bars=r[1], i=i)); poslednij = i
    return out

def kontrol(B, sdelki, seed=7):
    random.seed(seed); out = []
    for s in sdelki:
        b = B[s['sym']]
        for _ in range(5):
            k = random.randint(max(760, s['i'] - 720), min(len(b) - MAX_HOLD - 3, s['i'] + 720))
            a = mc.atr(b[k - 30:k + 1], 14); r = vedenie(b, k + 1, s['side'], b[k + 1][1])
            if r and a == a and r[2] <= MAX_RISK_ATR * a: out.append(r[0])
    return out

def svod(x):
    if len(x) < 3: return dict(n=len(x))
    R = [s['R'] for s in x]; eq = pk = dd = 0
    for s in sorted(x, key=lambda s: s['ts']):
        eq += s['R']; pk = max(pk, eq); dd = max(dd, pk - eq)
    return dict(n=len(x), R_sdelka=round(st.mean(R), 3), t=round(st.mean(R) / (st.stdev(R) / math.sqrt(len(R))), 2), itog_R=round(sum(R), 1),
                maxDD_R=round(dd, 1), vin=round(sum(r > 0 for r in R) / len(R), 2),
                S7_R=round(sum(s['R'] for s in x if s['sym'] in S7), 1), drugie_R=round(sum(s['R'] for s in x if s['sym'] not in S7), 1),
                drugie_n=sum(s['sym'] not in S7 for s in x), long_R=round(sum(s['R'] for s in x if s['side'] == 'long'), 1),
                short_R=round(sum(s['R'] for s in x if s['side'] == 'short'), 1))

if __name__ == '__main__':
    syms = sorted(p.split('/')[-1].split('_5_')[0] for p in glob.glob('/root/irv4/.cache/klines/*_5_*.json'))
    B = {s: chasy(s) for s in syms}
    rez = {}
    for nakl in (False, True):
        for brain in (False, True):
            sd = [x for s in syms for x in signaly(s, B[s], nakl, brain)]
            k = kontrol(B, sd)
            nm = f"naklonnaya={'ON' if nakl else 'OFF'} brain={'ON' if brain else 'OFF'}"
            rez[nm] = dict(svod(sd), kontrol_R=round(st.mean(k), 3) if k else None, kontrol_n=len(k))
            print(nm, rez[nm], flush=True)
    json.dump(rez, open('/root/struct/structural_v1_dev_20261021.json', 'w'), ensure_ascii=False, indent=1)
