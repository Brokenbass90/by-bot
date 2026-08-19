import json, os, random, sys
D="research_lab/data/movers_5m"
files=sorted(os.listdir(D)); random.seed(11); random.shuffle(files); files=files[:40]
def to_h1(rows):
    out=[];cur=None;h=None
    for b in rows:
        hh=b[0]//3600000
        if h!=hh:
            if cur: out.append(cur)
            cur=[b[0],b[1],b[2],b[3],b[4]];h=hh
        else:
            cur[2]=max(cur[2],b[2]);cur[3]=min(cur[3],b[3]);cur[4]=b[4]
    if cur: out.append(cur)
    return out
def all_pivots(rows,l=2,r=2):
    hi=[];lo=[]
    for i in range(l,len(rows)-r):
        v=rows[i][2]
        if all(v>=rows[j][2] for j in range(i-l,i)) and all(v>rows[j][2] for j in range(i+1,i+r+1)): hi.append((i,v))
        v=rows[i][3]
        if all(v<=rows[j][3] for j in range(i-l,i)) and all(v<rows[j][3] for j in range(i+1,i+r+1)): lo.append((i,v))
    return hi,lo
def fit(pts):
    n=len(pts);mx=sum(p[0] for p in pts)/n;my=sum(p[1] for p in pts)/n
    den=sum((p[0]-mx)**2 for p in pts)
    if den<=0: return None
    m=sum((p[0]-mx)*(p[1]-my) for p in pts)/den
    return m,my-m*mx
def atr_series(rows,n=14):
    out=[None]*len(rows);s=0.0;q=[]
    for i in range(1,len(rows)):
        tr=max(rows[i][2]-rows[i][3],abs(rows[i][2]-rows[i-1][4]),abs(rows[i][3]-rows[i-1][4]))
        q.append(tr);s+=tr
        if len(q)>n: s-=q.pop(0)
        if len(q)==n: out[i]=s/n
    return out
def rsi_series(rows,n=14):
    out=[None]*len(rows);g=[];l=[]
    for i in range(1,len(rows)):
        d=rows[i][4]-rows[i-1][4]
        g.append(max(d,0.0));l.append(max(-d,0.0))
        if len(g)>n: g.pop(0);l.pop(0)
        if len(g)==n:
            ag=sum(g)/n;al=sum(l)/n
            out[i]=100.0 if al==0 else 100-100/(1+ag/al)
    return out
CACHE={}
for fn in files:
    try: r5=json.load(open(os.path.join(D,fn)))
    except: continue
    if len(r5)<20000: continue
    h1=to_h1(r5)
    if len(h1)<400: continue
    CACHE[fn]=(h1,all_pivots(h1),atr_series(h1),rsi_series(h1))
print(f"монет: {len(CACHE)}")
def run(guard):
    tr=[]
    for fn,(h1,(PH,PL),AT,RS) in CACHE.items():
        n=len(h1)
        for i in range(140,n-49):
            a=AT[i]; rs=RS[i]
            if not a or a<=0: continue
            cur=h1[i][4];o=h1[i][1];hh=h1[i][2];ll=h1[i][3];rng=hh-ll
            if rng<=0 or abs(cur-o)<0.18*rng: continue
            r3=(h1[i][4]/h1[i-3][4]-1.0) if h1[i-3][4]>0 else 0.0
            r6=(h1[i][4]/h1[i-6][4]-1.0) if h1[i-6][4]>0 else 0.0
            for side,PV in (("short",PH),("long",PL)):
                if side=="short" and cur>=o: continue
                if side=="long" and cur<=o: continue
                if guard in ("A3","A3_RSI"):
                    if side=="short" and r3>0: continue
                    if side=="long" and r3<0: continue
                if guard=="A6":
                    if side=="short" and r6>0: continue
                    if side=="long" and r6<0: continue
                if guard in ("RSI","A3_RSI") and rs is not None:
                    if side=="short" and rs<60: continue
                    if side=="long" and rs>40: continue
                pts=[p for p in PV if p[0]<=i-3][-2:]
                if len(pts)<2: continue
                if i-pts[0][0]>120: continue
                f=fit(pts)
                if not f: continue
                m,b=f; lvl=m*i+b
                if abs(cur-lvl)>0.40*a: continue
                bad=False
                for k in range(pts[0][0],i):
                    c=h1[k][4]
                    if (side=="short" and c>m*k+b) or (side=="long" and c<m*k+b): bad=True;break
                if bad: continue
                sl=lvl+a if side=="short" else lvl-a
                risk=abs(sl-cur)
                if risk<=0: continue
                tp=cur-2*risk if side=="short" else cur+2*risk
                out=None
                for j in range(i+1,min(i+49,n)):
                    if side=="short":
                        if h1[j][2]>=sl: out=-1.0;break
                        if h1[j][3]<=tp: out=2.0;break
                    else:
                        if h1[j][3]<=sl: out=-1.0;break
                        if h1[j][2]>=tp: out=2.0;break
                if out is None:
                    px=h1[min(i+48,n-1)][4]
                    out=((cur-px) if side=="short" else (px-cur))/risk
                tr.append((h1[i][0],out))
    return tr
def summ(t):
    if len(t)<30: return None
    t.sort();r=[x for _,x in t];n=len(r);m=sum(r)/n
    gp=sum(x for x in r if x>0);gl=-sum(x for x in r if x<0);h=n//2
    return dict(n=n,exp=round(m,4),win=round(sum(1 for x in r if x>0)/n*100,1),
                pf=round(gp/gl,3) if gl>0 else 99.9,
                h1=round(sum(r[:h])/h,4),h2=round(sum(r[h:])/(n-h),4))
print("\nguard    |    n | ожидание R | win% | PF    | 1-я пол | 2-я пол")
for g in (None,"A3","A6","RSI","A3_RSI"):
    s=summ(run(g))
    nm=g or "БЕЗ guard"
    if not s: print(f"{nm:<8} | мало сделок"); continue
    mark=" <<<" if s['exp']>0.0191 and s['h1']>0 and s['h2']>0 else ""
    print(f"{nm:<8} | {s['n']:>4} | {s['exp']:>10} | {s['win']:>4} | {s['pf']:>5} | {s['h1']:>7} | {s['h2']:>7}{mark}")
