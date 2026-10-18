import math
def se_R(o):
    v = o.get('se', 0) ** 2 - o.get('ctrl_sd', 0) ** 2
    return math.sqrt(v) if v > 0 else None
def sudya_dengi(rez, min_n=50, min_n_o3=30):
    ok = rez['okna']; o1, o2, o3 = ok.get('O1', {}), ok.get('O2', {}), ok.get('O3')
    for o in (o1, o2):
        if o.get('n', 0) < min_n or 'mean' not in o: return 'MONEY_LOW_N'
    s1, s2 = se_R(o1), se_R(o2)
    if not s1 or not s2: return 'MONEY_LOW_N'
    w = [(o1['mean'], s1), (o2['mean'], s2)]; sw = sum(1 / s ** 2 for _, s in w)
    t = sum(m / s ** 2 for m, s in w) / sw * math.sqrt(sw)
    if not (o1['mean'] > 0 and o2['mean'] > 0 and t >= 2.0): return f'MONEY_FAIL(t={t:.2f})'
    if o3 is not None and o3.get('n', 0) >= min_n_o3 and 'mean' in o3:
        return f'MONEY_PASS(t={t:.2f},O3={o3["mean"]:+.3f})' if o3['mean'] > 0 else f'MONEY_FAIL_O3(t={t:.2f})'
    return f'MONEY_PASS_BEZ_O3(t={t:.2f})'
