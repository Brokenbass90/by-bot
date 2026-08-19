import json, os, random, statistics
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
def atr_series(rows,n=14):
    out=[None]*len(rows);q=[];s=0.0
    for i in range(1,len(rows)):
        tr=max(rows[i][2]-rows[i][3],abs(rows[i][2]-rows[i-1][4]),abs(rows[i][3]-rows[i-1][4]))
        q.append(tr);s+=tr
        if len(q)>n: s-=q.pop(0)
        if len(q)==n: out[i]=s/n
    return out
def sma(rows,n):
    out=[None]*len(rows);s=0.0
    for i,r in enumerate(rows):
        s+=r[4]
        if i>=n: s-=rows[i-n][4]
        if i>=n-1: out[i]=s/n
    return out
CACHE={}
for fn in files:
    try: r5=json.load(open(os.path.join(D,fn)))
    except: continue
    if len(r5)<20000: continue
    h1=to_h1(r5)
    if len(h1)<600: continue
    CACHE[fn]=(h1,atr_series(h1),sma(h1,20),sma(h1,50*24))
print(f"монет: {len(CACHE)}")
FEE=0.00075
def walk(h1,i,side,entry,sl,tp,maxh=48):
    n=len(h1)
    risk=abs(sl-entry)
    if risk<=0: return None,None
    for j in range(i+1,min(i+maxh+1,n)):
        if side=="long":
            if h1[j][3]<=sl: return -1.0,risk/entry
            if h1[j][2]>=tp: return (tp-entry)/risk, risk/entry
        else:
            if h1[j][2]>=sl: return -1.0,risk/entry
            if h1[j][3]<=tp: return (entry-tp)/risk, risk/entry
    px=h1[min(i+maxh,n-1)][4]
    return (((px-entry) if side=="long" else (entry-px))/risk), risk/entry
def run(fam):
    tr=[]
    for fn,(h1,AT,S20,S50D) in CACHE.items():
        n=len(h1)
        for i in range(200,n-49):
            a=AT[i]
            if not a or a<=0: continue
            c=h1[i][4];o=h1[i][1];hi=h1[i][2];lo=h1[i][3]
            if fam=="RANGE":
                w=h1[i-48:i]
                hh=max(x[2] for x in w); ll=min(x[3] for x in w)
                if hh-ll > 1.5*a or hh<=ll: continue
                if c <= ll + 0.15*(hh-ll):
                    r=walk(h1,i,"long",c,ll-0.5*a,hh)
                elif c >= hh - 0.15*(hh-ll):
                    r=walk(h1,i,"short",c,hh+0.5*a,ll)
                else: continue
            elif fam=="BOUNCE":
                w=h1[i-120:i]
                hh=max(x[2] for x in w); ll=min(x[3] for x in w)
                rng=hi-lo
                if rng<=0 or abs(c-o)<0.2*rng: continue
                if abs(c-ll)<=0.3*a and c>o:
                    r=walk(h1,i,"long",c,c-a,c+2*a)
                elif abs(c-hh)<=0.3*a and c<o:
                    r=walk(h1,i,"short",c,c+a,c-2*a)
                else: continue
            else:  # ELDER
                d=S50D[i]; m=S20[i]
                if d is None or m is None or i<24: continue
                dprev=S50D[i-24]
                if dprev is None: continue
                up = d>dprev
                if up and lo<=m<=c and c>o:
                    r=walk(h1,i,"long",c,c-a,c+2*a)
                elif (not up) and c<=m<=hi and c<o:
                    r=walk(h1,i,"short",c,c+a,c-2*a)
                else: continue
            if r[0] is None: continue
            tr.append((h1[i][0], r[0], r[1]))
    return tr
print("\nсемейство |    n | риск,%цены | ожид. БЕЗ комис | комис.в R | ЧИСТОЕ | win% | 1-я пол | 2-я пол")
for fam in ("RANGE","BOUNCE","ELDER"):
    t=run(fam)
    if len(t)<200:
        print(f"{fam:<9} | {len(t):>4} | мало сделок"); continue
    t.sort()
    r=[x[1] for x in t]; rk=statistics.median([x[2] for x in t])
    fee_R=FEE/rk
    net=[x-fee_R for x in r]
    n=len(net); h=n//2
    ex=sum(net)/n; win=sum(1 for x in net if x>0)/n*100
    h1v=sum(net[:h])/h; h2v=sum(net[h:])/(n-h)
    mark=" <<<" if ex>0 and h1v>0 and h2v>0 else ""
    print(f"{fam:<9} | {n:>4} | {rk*100:>10.2f} | {sum(r)/n:>15.4f} | {fee_R:>9.4f} | {ex:>+6.4f} | {win:>4.1f} | {h1v:>+7.4f} | {h2v:>+7.4f}{mark}")
