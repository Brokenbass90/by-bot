import sys, statistics as st, math
sys.path.insert(0,'/root/struct'); sys.path.insert(0,'/root/devfix')
import v2_diag as D
import bot.market_context as mc
def run(vh, cap):
    g=[]; n_=[]; kept=0
    for s,i,sd,e in vh:
        b=D.B[s]; a=mc.atr(b[i-31:i],14); p=D.put(b,i,sd,e)
        if p is None or not(a==a and a>0): continue
        if cap and p['risk']>D.S.MAX_RISK_ATR*a: continue
        sgn=1 if sd=='long' else -1; gross=sgn*(p['exit']-e)/p['risk']; cost=2*D.FEE*e/p['risk']
        g.append(gross); n_.append(cost)
    t=lambda x: round(st.mean(x)/(st.stdev(x)/math.sqrt(len(x))),2)
    net=[a-b for a,b in zip(g,n_)]
    return dict(n=len(g), R_do_rashodov=round(st.mean(g),3), rashody_R=round(st.mean(n_),3), R_posle=round(st.mean(net),3), t_posle=t(net))
v4=D.vhody_v4(); v1=D.vhody_v1()
print('v4 входы, без лимита риска', run(v4, False)); print('v4 входы, риск ≤ 3 ATR', run(v4, True))
print('V1 входы, риск ≤ 3 ATR', run(v1, True))
