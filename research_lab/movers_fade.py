"""Фейд импульса на свежих монетах: плато по горизонту + разбиение монет на две непересекающиеся группы."""
import json, os, random, sys
D="research_lab/data/movers_5m"
files=sorted(os.listdir(D)); random.seed(7); random.shuffle(files)
part=sys.argv[1]; K=60
files = files[:K] if part=="A" else files[K:2*K]
res={}; nsym=0
for fn in files:
    try: rows=json.load(open(os.path.join(D,fn)))
    except: continue
    if len(rows)<500: continue
    nsym+=1
    c=[r[4] for r in rows]; v=[r[5] for r in rows]; n=len(c)
    for i in range(60,n-45):
        vm=sum(v[i-20:i])/20.0
        if vm<=0: continue
        ret=c[i]/c[i-1]-1.0
        if abs(ret)<0.02 or v[i]<3*vm: continue
        d=1 if ret>0 else -1
        for H in (6,9,12,15,18,24,36):
            j=i+H
            if j<n: res.setdefault(H,[]).append(-d*(c[j]/c[i]-1.0))
print(f"ГРУППА {part}: монет {nsym}")
print("горизонт | n     | сырой bps | МЕЙКЕР -4bps | win%")
for H in sorted(res):
    v=res[H]
    if len(v)<200: continue
    m=sum(v)/len(v)*10000; w=sum(1 for x in v if x>0)/len(v)*100
    fl=" <<<" if m-4>0 else ""
    print(f"{H*5:>5}м | {len(v):<5} | {m:>9.2f} | {m-4:>12.2f} | {w:.1f}%{fl}")
