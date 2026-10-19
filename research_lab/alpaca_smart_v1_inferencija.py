import json, math, numpy as np
from statistics import NormalDist
rng=np.random.default_rng(20261019)
def nw(x,lag):
    x=np.asarray(x,float);n=len(x);e=x-x.mean();s=(e@e)/n
    for L in range(1,lag+1): s+=2*(1-L/(lag+1))*(e[L:]@e[:-L])/n
    return x.mean()/math.sqrt(s/n), (e@e)/n/s if s>0 else None
def mbb(x,b,R=20000):
    x=np.asarray(x,float);n=len(x);nb=math.ceil(n/b);m=np.empty(R)
    starts=rng.integers(0,n-b+1,size=(R,nb))
    for r in range(R):
        idx=(starts[r][:,None]+np.arange(b)).ravel()[:n]; m[r]=x[idx].mean()
    lo,hi=np.percentile(m,[2.5,97.5]); p=2*min((m<=0).mean(),(m>=0).mean())
    # p under null: recentered
    c=m-x.mean(); p0=(np.abs(c)>=abs(x.mean())).mean()
    return dict(mean=float(x.mean()),ci95=[float(lo),float(hi)],p_boot=float(p0),se_boot=float(m.std()))
out={}
for u in ("U2","U58"):
    d=json.load(open(f"smart_{u}.json"))["syrye_ic"]
    for h in ("21","42"):
        rr=d[h]; lag=1 if h=="21" else 2; b=3 if h=="21" else 4
        for nm,ser in (("H1_inc",[x["ic_resid"]-x["ic_raw"] for x in rr]),("H2_stab",[x["ic_stab"] for x in rr])):
            t,ratio=nw(ser,lag); bs=mbb(ser,b); n=len(ser)
            out[f"{u}_{h}_{nm}"]=dict(n_dat=n,t_NW=round(t,3),n_eff_NW=round(n*ratio,1) if ratio else None,
              t_iid=round(np.mean(ser)/(np.std(ser,ddof=1)/math.sqrt(n)),3),boot_blok=b,**{k:(round(v,4) if isinstance(v,float) else [round(z,4) for z in v]) for k,v in bs.items()})
for k,v in out.items(): print(k,v)
z=NormalDist().inv_cdf
print("t_req k=2:",round(z(1-0.05/4),3)," k=4 (2 hyp x 2 hor):",round(z(1-0.05/8),3)," k=8 (x2 univ):",round(z(1-0.05/16),3))
json.dump(out,open("/mnt/user-data/outputs/smart/smart_inferencija.json","w"),ensure_ascii=False,indent=1)
