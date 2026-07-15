"""RESEARCH STATION v2 — дисциплинированный массовый поиск, RESUMABLE (изолирован от прода).

Защита от переобучения: кандидат выживает ТОЛЬКО на невиданных данных (in-sample gate ->
forward-holdout -> oos-symbol holdout). Все детали гейта: bot/wf_folds + oos_selector + loso.

RESUMABLE: каждый завершённый вариант дописывается в results/{run_id}.jsonl (append-only).
При перезапуске (сон/выключение/краш) уже сделанные варианты ПРОПУСКАЮТСЯ -> продолжает с места.
Прогон НЕ в проде. Долгий запуск — на Mac через run_station.sh (caffeinate + автоперезапуск).
"""
from __future__ import annotations
import sys, json, glob, itertools, os, hashlib, time
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backtest.engine import Candle, KlineStore, BacktestParams, run_symbol_backtest
from bot.wf_folds import purge_embargo_folds
from bot.oos_selector import evaluate_candidate
from bot.loso_concentration import loso_check

RESULTS_DIR=os.path.join(ROOT,"research_lab","results")
os.makedirs(RESULTS_DIR, exist_ok=True)
_CACHE={}
def load(sym, cap=200000):
    if sym in _CACHE: return _CACHE[sym]
    import os as _o
    fs=sorted(glob.glob(f"{ROOT}/data_cache/{sym}_5_*.json"), key=lambda f:_o.path.getsize(f))
    if not fs: _CACHE[sym]=None; return None
    d=json.load(open(fs[-1])); rows=d if isinstance(d,list) else d.get("data")
    g=lambda r,k,i:(r[k] if isinstance(r,dict) else r[i])
    cs=[Candle(ts=int(g(r,'ts',0)),o=float(g(r,'o',1)),h=float(g(r,'h',2)),l=float(g(r,'l',3)),c=float(g(r,'c',4)),v=float(g(r,'v',5) or 0)) for r in rows][-cap:]
    _CACHE[sym]=cs; return cs
P=dict(starting_equity=1000.0,risk_pct=0.01,cap_notional_usd=1000.0,leverage=1.0,max_positions=1,fee_bps=6.0,slippage_bps=2.0,entry_on_next_open=True)

def _bt(factory, symbols, part):
    trades=[]; by={}
    for sym in symbols:
        cs=load(sym)
        if not cs: continue
        if part=="first": cs=cs[:len(cs)//2]
        elif part=="second": cs=cs[len(cs)//2:]
        st=KlineStore(sym,cs,base_interval_min=5)
        strat=factory()
        def sf(s_o,bar,strat=strat):
            try: return strat.maybe_signal(s_o,int(bar.ts),float(bar.o),float(bar.h),float(bar.l),float(bar.c),float(bar.v))
            except Exception: return None
        tr,_=run_symbol_backtest(st,strategy_name="x",signal_fn=sf,params=BacktestParams(**P))
        for t in tr: trades.append({"entry_ts":t.entry_ts,"exit_ts":t.exit_ts,"r":t.pnl/10.0}); by.setdefault(sym,[]).append(t.pnl/10.0)
    return trades, by
def _gate(trades, by, min_n=30):
    if len(trades)<min_n: return False,f"low_N_{len(trades)}"
    fs=purge_embargo_folds(trades,n_folds=4,embargo=6*3600*1000)
    rep=evaluate_candidate({"id":"c","folds":[{"trades":f["trades"],"net_r":f["net_r"]} for f in fs.folds]},min_folds=3,min_frac_positive=0.75,min_trades_total=min_n,min_trades_per_fold=3)
    if not rep.passes: return False,"folds_"+rep.reason
    lo=loso_check(by)
    return (lo.passes, "PASS" if lo.passes else "loso_"+lo.reason)

def _key(name, params): return hashlib.sha1((name+json.dumps(params,sort_keys=True)).encode()).hexdigest()[:12]

def run(run_id, registry, is_symbols, oos_symbols):
    """registry: list of (name, builder(params)->factory, param_grid dict). RESUMABLE."""
    path=os.path.join(RESULTS_DIR, f"{run_id}.jsonl")
    done=set()
    if os.path.exists(path):
        for line in open(path):
            try: done.add(json.loads(line)["key"])
            except Exception: pass
    print(f"[{run_id}] уже сделано ранее: {len(done)} вариантов (resume)")
    total=0; tested=0; survivors=0
    for name, builder, grid in registry:
        keys=list(grid); combos=list(itertools.product(*[grid[k] for k in keys]))
        total+=len(combos)
        for vals in combos:
            params=dict(zip(keys,vals)); k=_key(name,params)
            if k in done: continue
            fac=builder(params)
            tr,by=_bt(fac,is_symbols,"first"); ok,reason=_gate(tr,by)
            rec={"key":k,"strategy":name,"params":params,"is_pass":ok,"is_reason":reason,"ts":int(time.time())}
            if ok:  # forward + oos holdout
                tr2,by2=_bt(fac,is_symbols,"second"); ok2,r2=_gate(tr2,by2)
                tr3,by3=_bt(fac,oos_symbols,"all"); ok3,r3=_gate(tr3,by3)
                rec["fwd_pass"]=ok2; rec["oos_sym_pass"]=ok3; rec["survivor"]=bool(ok2 and ok3)
                if rec["survivor"]:
                    survivors+=1; rec["is_net_r"]=round(sum(t["r"] for t in tr),2)
                    print(f"  🟢 SURVIVOR {name} {params} is={rec['is_net_r']}R")
            with open(path,"a") as f: f.write(json.dumps(rec)+"\n")  # append after EACH -> resumable
            tested+=1
            if tested%25==0: print(f"  ... протестировано {tested} новых, выживших {survivors}", flush=True)
    print(f"[{run_id}] ГОТОВО: total={total} tested_new={tested} survivors={survivors}. Результаты: {path}")

# ---- ШИРОКОЕ ПРОСТРАНСТВО ПОИСКА (расширяй здесь) ----
import math
class _LevelFadeRegime:
    """Самодостаточная регим-гейтед фейд-логика (параметризуемая) для поиска."""
    def __init__(self, er_thresh, lookback, band, rr):
        self.er_thresh=er_thresh; self.lookback=lookback; self.band=band; self.rr=rr
    def maybe_signal(self, store, ts_ms, o,h,l,c,v=0.0):
        rows=store.fetch_klines(store.symbol,"5",288) or []
        if len(rows)<280: return None
        hi=[float(r[2]) for r in rows]; lo=[float(r[3]) for r in rows]; cl=[float(r[4]) for r in rows]
        n=len(cl)
        trs=[max(hi[i]-lo[i],abs(hi[i]-cl[i-1]),abs(lo[i]-cl[i-1])) for i in range(n-14,n)]
        a=sum(trs)/14
        if a<=0: return None
        # Kaufman ER: high=trend, low=range
        direction=abs(cl[-1]-cl[-1-24]); vol=sum(abs(cl[i]-cl[i-1]) for i in range(n-24,n))
        er=direction/vol if vol>0 else 1.0
        if er>=self.er_thresh: return None  # только боковик
        price=cl[-1]; tol=self.band*a
        rng_hi=max(hi[-self.lookback:]); rng_lo=min(lo[-self.lookback:])
        from strategies.signals import TradeSignal
        if hi[-1]>=rng_hi-0.15*a and cl[-1]<rng_hi and (hi[-1]-cl[-1])>0.4*(hi[-1]-lo[-1]+1e-9):
            e=price; sl=rng_hi+0.6*a; risk=sl-e
            if risk<=0 or risk/e<0.004: return None
            return TradeSignal(strategy="lfr",symbol=store.symbol,side="short",entry=e,sl=sl,tp=e-self.rr*risk,tps=[e-self.rr*risk],tp_fracs=[1.0],time_stop_bars=96)
        if lo[-1]<=rng_lo+0.15*a and cl[-1]>rng_lo and (cl[-1]-lo[-1])>0.4*(hi[-1]-lo[-1]+1e-9):
            e=price; sl=rng_lo-0.6*a; risk=e-sl
            if risk<=0 or risk/e<0.004: return None
            return TradeSignal(strategy="lfr",symbol=store.symbol,side="long",entry=e,sl=sl,tp=e+self.rr*risk,tps=[e+self.rr*risk],tp_fracs=[1.0],time_stop_bars=96)
        return None

def build_registry():
    os.environ.setdefault("ATT1_SIGNAL_TF","60")
    reg=[]
    # 1) att1 param sweep (наклонная трендовая)
    from strategies.alt_trendline_touch_v1 import AltTrendlineTouchV1Strategy
    def att1_builder(p):
        def fac():
            os.environ["ATT1_TP1_RR"]=str(p["tp1"]); os.environ["ATT1_TP2_RR"]=str(p["tp2"]); os.environ["ATT1_TRAIL_ATR_MULT"]=str(p["trail"])
            return AltTrendlineTouchV1Strategy()
        return fac
    reg.append(("att1", att1_builder, {"tp1":[1.0,1.2,1.5],"tp2":[2.0,2.5,3.5,5.0],"trail":[1.0,1.5,2.5]}))
    # 2) НОВАЯ ЛОГИКА: regime-gated level-fade sweep (боковик-фейд)
    def lfr_builder(p):
        def fac(): return _LevelFadeRegime(p["er"],p["lb"],p["band"],p["rr"])
        return fac
    reg.append(("levelfade_regime", lfr_builder, {"er":[0.20,0.30,0.40],"lb":[15,20,30],"band":[0.2,0.4],"rr":[1.5,2.0,2.5]}))
    # 3) pump_fade_simple sweep (памп-фейд на микрокапах)
    try:
        from strategies.pump_fade_simple import PumpFadeSimpleStrategy, PumpFadeSimpleConfig
        def pf_builder(p):
            def fac():
                cfg=PumpFadeSimpleConfig(); cfg.pump_threshold_pct=p["thr"]; cfg.rsi_overbought=p["rsi"]; cfg.rr=p["rr"]
                return PumpFadeSimpleStrategy(cfg)
            return fac
        reg.append(("pump_fade_simple", pf_builder, {"thr":[0.06,0.08,0.12],"rsi":[70,75],"rr":[1.6,2.0]}))
    except Exception:
        pass
    # 4) КЛАССИКА (запрос владельца): элдер, пробои, ретесты, пила, среднесрок — честный тест на глубоких данных
    def _simple(mod_path, cls_name):
        def builder(pp):
            def fac():
                import importlib
                m=importlib.import_module(mod_path)
                return getattr(m,cls_name)()
            return fac
        return builder
    classics=[
        ("elder","strategies.elder_triple_screen_v2","ElderTripleScreenV2Strategy"),
        ("horizontal_break","strategies.alt_horizontal_break_v1","AltHorizontalBreakV1Strategy"),
        ("range_scalp","strategies.alt_range_scalp_v1","AltRangeScalpV1Strategy"),
        ("impulse_breakout","strategies.impulse_volume_breakout_v1","ImpulseVolumeBreakoutV1Strategy"),
        ("midterm_v3","strategies.btc_eth_midterm_v3","BTCETHMidtermV3Strategy"),
    ]
    for nm,mp,cn in classics:
        try:
            reg.append((nm, _simple(mp,cn), {"variant":[0]}))  # дефолт-конфиг, честный прогон на 2г×8монет
        except Exception:
            pass
    # TODO Codex: развернуть параметр-гриды каждой классики (env-свипы) -> тысячи комбо.
    return reg

if __name__=="__main__":
    run_id=sys.argv[1] if len(sys.argv)>1 else "station_demo"
    IS=["BTCUSDT","ETHUSDT","SOLUSDT","ADAUSDT","LINKUSDT","AVAXUSDT","XRPUSDT","DOGEUSDT"]; OOS=["ATOMUSDT","DOTUSDT","LTCUSDT","1000PEPEUSDT"]
    run(run_id, build_registry(), IS, OOS)
