#!/usr/bin/env python3
"""Инвентарь корпуса strategies/: запускается ли стратегия на часовых барах текущего склада, сколько сигналов, какие
таймфреймы склад отказал отдать, ошибки. БЕЗ доходностей (не тратит бюджет проверок). Состояние — инкрементально.
python3 research_lab/inventar_strategiy.py [--po N]"""
import importlib, inspect, json, os, subprocess, sys, time
from pathlib import Path
KOREN = Path(__file__).resolve().parents[1]; os.chdir(KOREN)
OUT = Path("research_lab/data/inventar_strategiy_20261020.json")
SIMV = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "1000PEPEUSDT")
OKNO = 4000
KOD = r'''
import sys, json, importlib, inspect, collections, numpy as np, traceback
sys.path.insert(0,"."); sys.path.insert(0,"research_lab")
from research_machine import Store, pervyy_argument
mod=sys.argv[1]; m=importlib.import_module("strategies."+mod)
kl=[o for _,o in vars(m).items() if inspect.isclass(o) and hasattr(o,"maybe_signal") and o.__module__==m.__name__]
res={}
for K in kl:
    r=dict(signalov=0, storony=collections.Counter(), oshibok=0, otkazy={}, pervaya_oshibka=None)
    for sym in %s:
        try: s=K()
        except Exception as e: r["oshibka_sozdaniya"]=repr(e)[:200]; break
        d=np.load(f"research_lab/data/h1/{sym}.npz"); ts=d["ts"]; o=d["ohlcv"].astype(float)
        b=[[int(ts[x]),*map(float,o[x])] for x in range(len(ts))][-%d:]
        st=Store(sym); pv=sym if pervyy_argument(K)=="symbol" else st
        for i in range(200,len(b)-1):
            st.rows=b[:i+1]; x=b[i]
            try:
                g=s.maybe_signal(pv,x[0],x[1],x[2],x[3],x[4],x[5])
                if g is not None and getattr(g,"side",None) in ("long","short"): r["signalov"]+=1; r["storony"][g.side]+=1
            except Exception as e:
                r["oshibok"]+=1
                if r["pervaya_oshibka"] is None: r["pervaya_oshibka"]=traceback.format_exc()[-300:]
        for k,v in getattr(st,"otkazy",{}).items(): r["otkazy"][str(k)]=r["otkazy"].get(str(k),0)+v
    r["storony"]=dict(r["storony"]); res[K.__name__]=r
print(json.dumps(res))
''' % (repr(SIMV), OKNO)

def main():
    po = int(sys.argv[sys.argv.index("--po") + 1]) if "--po" in sys.argv else 999
    st = json.loads(OUT.read_text()) if OUT.exists() else {}
    mods = sorted(p.stem for p in Path("strategies").glob("*.py") if not p.stem.startswith("_") and p.stem not in ("signals", "__init__"))
    sdelano = 0
    for mod in mods:
        if mod in st or sdelano >= po: continue
        t = time.time()
        try:
            p = subprocess.run([sys.executable, "-c", KOD, mod], capture_output=True, text=True, timeout=45)
            st[mod] = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 and p.stdout.strip() else {"oshibka_importa": (p.stderr or "")[-300:]}
        except subprocess.TimeoutExpired:
            st[mod] = {"medlennaya": ">45 с"}
        except Exception as e:
            st[mod] = {"oshibka_zapuska": repr(e)[:200]}
        st[mod]["_sek"] = round(time.time() - t, 1); sdelano += 1
        OUT.write_text(json.dumps(st, ensure_ascii=False, indent=1))
    print(len(st), "из", len(mods))

if __name__ == "__main__":
    main()
