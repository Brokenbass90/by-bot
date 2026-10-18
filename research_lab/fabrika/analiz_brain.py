import json, glob, os, math, collections, sys
import numpy as np
D = os.path.expanduser('~/w/fab/rez_brain')
K = {'kanal': {0: 'NET', 1: 'VVERH', 2: 'VNIZ', 3: 'FLET'}, 'vol': {0: 'NIZK', 1: 'SRED', 2: 'VYSOK'}, 'trend': {1: 'UP', -1: 'DOWN'}}
def stat(x):
    x = np.array(x); n = len(x)
    if n < 3: return n, float('nan'), float('nan')
    m = x.mean(); se = x.std(ddof=1) / math.sqrt(n); return n, m, m / se if se > 0 else 0.0
out = []; kand = []
for f in sorted(glob.glob(D + '/*.json')):
    d = json.load(open(f)); tag = os.path.basename(f)[:-5]
    sd = [s for s in d.get('sdelki', []) if s['ctrl'] is not None]
    disc = [s for s in sd if s['okno'] in ('O1', 'O2')]; hold = [s for s in sd if s['okno'] == 'O3']
    n0, m0, z0 = stat([s['R'] - s['ctrl'] for s in disc])
    for dim, mp in K.items():
        for code, name in mp.items():
            x = [s['R'] - s['ctrl'] for s in disc if s[dim] == code]
            n, m, z = stat(x)
            row = dict(id=tag, dim=dim, rezhim=name, n=n, edge=m, z=z, edge_bez=m0, z_bez=z0)
            if n >= 50 and z >= 3.1 and m > m0:
                y = [s['R'] - s['ctrl'] for s in hold if s[dim] == code]
                n3, m3, z3 = stat(y); row.update(n_O3=n3, edge_O3=m3, z_O3=z3,
                    verdikt=('BRAIN_HELPS' if n3 >= 30 and m3 > 0 else ('UNKNOWN' if n3 < 30 else 'FAIL')))
                kand.append(row)
            out.append(row)
json.dump(dict(yacheyki=out, kandidaty=kand), open(os.path.expanduser('~/w/fab/brain_svodka.json'), 'w'), ensure_ascii=False, indent=1, default=float)
print('par', len(set(r['id'] for r in out)), 'yacheek', len(out), 'kandidatov', len(kand))
for r in kand: print(r)
# сводка: режимы, где эдж стабильно хуже/лучше в среднем по всем стратегиям (отчётно)
agg = collections.defaultdict(list)
for r in out:
    if r['n'] >= 50 and not math.isnan(r['edge']): agg[(r['dim'], r['rezhim'])].append(r['edge'] - r['edge_bez'])
for k, v in sorted(agg.items()): print(k, 'par', len(v), 'srednyaya raznica k bez filtra', round(float(np.mean(v)), 4), 'dolya luchshe', round(float(np.mean(np.array(v) > 0)), 2))
