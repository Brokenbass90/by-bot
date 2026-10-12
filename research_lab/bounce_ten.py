#!/usr/bin/env python3
"""bounce_ten.py — проспективная тень BOUNCE1 на закрытых H1 Bybit (только публичные данные, без ключей и заявок).
Заменяет недоказуемую тень VPS с 08.08 (Codex: ledger отсутствует, вселенная другая, счёт UNKNOWN). Эпоха = первый запуск --cikl.
Механика = исследовательская: сигнал на закрытом H1-баре (стратегия alt_support_bounce_v1 as is, замороженный env),
вход next-open, выход orchestrator.simulate (стоп раньше целей, удержание 48 ч = time_stop 576×5m, mult 1.0),
издержки 6 bps/сторона в R + 2 bps/сторона проскальзывание, фандинг F1 (PREREG_BOUNCE1_KEEP_KILL §1) по Bybit API.
Варианты (раздельные журналы/ID): --variant BOUNCE1 (BTC,ETH) | BOUNCE1_8 (BTC,ETH,SOL,ADA,LINK,LTC,DOT,SUI).
    .venv/bin/python research_lab/bounce_ten.py --variant BOUNCE1 --cikl      (proverka: --proverka)"""
import argparse, datetime as dt, hashlib, json, os, sys, time, urllib.parse, urllib.request
from pathlib import Path
LAB = Path(__file__).resolve().parent; sys.path.insert(0, str(LAB)); sys.path.insert(0, str(LAB.parent))
VARIANTY = {"BOUNCE1": ["BTCUSDT", "ETHUSDT"],
            "BOUNCE1_8": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "DOTUSDT", "SUIUSDT"]}
ENV = {"ENABLE_BOUNCE1_TRADING": "1", "BOUNCE1_RISK_MULT": "1.0", "BOUNCE1_ALLOW_LONGS": "1", "BOUNCE1_ALLOW_SHORTS": "0",
       "BOUNCE1_SL_ATR_MULT": "1.6", "BOUNCE1_TP1_FRAC": "0.15", "BOUNCE1_TRAIL_ATR_MULT": "0.0", "BOUNCE1_COOLDOWN_BARS_5M": "6"}
H = 3600000; HOLD = 48; LOOKBACK = 400; SLIP = 0.0002
def utc(): return dt.datetime.now(dt.timezone.utc)
def log(*a): print(utc().isoformat(timespec="seconds"), *a, flush=True)

def get(put, **p):
    url = "https://api.bybit.com" + put + "?" + urllib.parse.urlencode(p)
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-paper"}), timeout=30) as r:
                j = json.loads(r.read()); time.sleep(0.15)
                if j.get("retCode") == 0: return j["result"]
        except Exception: pass
        time.sleep(5 * (k + 1))
    raise RuntimeError(f"Bybit не ответил {put}")

def h1(sym, n=LOOKBACK):
    now = int(time.time() * 1000) // H * H
    r = get("/v5/market/kline", category="linear", symbol=sym, interval="60", end=now - 1, limit=min(n, 1000))
    rows = sorted(([int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in r["list"]), key=lambda x: x[0])
    return [x for x in rows if x[0] + H <= now]          # только закрытые

def fanding(sym, t0, t1):
    r = get("/v5/market/funding/history", category="linear", symbol=sym, startTime=t0 + 1, endTime=t1, limit=200)
    st = sorted((int(x["fundingRateTimestamp"]), float(x["fundingRate"])) for x in r.get("list", []) if t0 < int(x["fundingRateTimestamp"]) <= t1)
    for a, b in zip([t0] + [t for t, _ in st], [t for t, _ in st] + [t1]):    # F1: разрыв > 8 ч 1 мин → неизвестно
        if b - a > 8 * H + 60000: return None
    return sum(v for _, v in st)

class Ten:
    def __init__(self, var):
        os.environ.update(ENV); os.environ["BOUNCE1_SYMBOL_ALLOWLIST"] = ",".join(VARIANTY[var])
        import importlib, research_machine as RM, orchestrator as O
        self.RM, self.O = RM, O; self.var = var
        self.D = LAB / "data" / f"bounce_ten_{var}"; self.D.mkdir(parents=True, exist_ok=True)
        self.jr = self.D / "zhurnal.jsonl"; ep = self.D / "EPOHA.json"
        if not ep.exists():
            src = (LAB.parent / "strategies/alt_support_bounce_v1.py").read_bytes()
            ep.write_text(json.dumps(dict(epoha_ms=int(time.time() * 1000) // H * H, variant=var, simvoly=VARIANTY[var], env=ENV,
                          strategy_sha256=hashlib.sha256(src).hexdigest(), kod_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()), indent=1))
        self.epoha = json.loads(ep.read_text())["epoha_ms"]
        S = getattr(importlib.import_module("strategies.alt_support_bounce_v1"), "AltSupportBounceV1Strategy"); self.S = S

    def zapisi(self):
        return [json.loads(l) for l in self.jr.read_text().splitlines()] if self.jr.exists() else []

    def shag(self):
        zap = {(z["sym"], z["ts"]): z for z in self.zapisi()}
        for sym in VARIANTY[self.var]:
            bars = h1(sym); st = self.RM.Store(sym); strat = self.S(); perv = self.RM.pervyy_dlya(self.S, st, sym)
            for i in range(120, len(bars)):                  # детерминированный прогрев: одна и та же история → тот же сигнал
                st.rows = bars[:i + 1]; b = bars[i]
                try: s = strat.maybe_signal(perv, b[0], b[1], b[2], b[3], b[4], b[5])
                except Exception as e: log("сбой стратегии", sym, type(e).__name__); continue
                if s is None or s.side != "long" or b[0] < self.epoha or (sym, b[0]) in zap: continue
                z = dict(variant=self.var, sym=sym, ts=b[0], sl=s.sl, tps=list(s.tps or []), f1=(s.tp_fracs or [0.55])[0], status="OTKRYTA",
                         zapisano=int(time.time() * 1000))
                zap[(sym, b[0])] = z; self.dobavit(z); log("СИГНАЛ", sym, dt.datetime.utcfromtimestamp(b[0] / 1000))
            idx = {x[0]: k for k, x in enumerate(bars)}
            for z in [z for z in zap.values() if z["sym"] == sym and z["status"] == "OTKRYTA"]:
                i = idx.get(z["ts"])
                if i is None: continue
                r = self.O.simulate(bars, i, "long", z["sl"], z["tps"], z["f1"], 1.0, HOLD)
                if r is None: continue
                e = i + 1; konec = e + r["bars"]
                if konec >= len(bars) - 1 and r["bars"] < HOLD - 1: continue        # выход ещё не определён закрытыми барами
                t_in, t_out = bars[e][0], bars[konec][0] + H
                f = fanding(sym, t_in, t_out)
                z.update(status="ZAKRYTA" if f is not None else "FUNDING_UNKNOWN", R_ceny=r["R"], lev=r["lev"],
                         R=None if f is None else r["R"] - 2 * SLIP * r["lev"] - f * r["lev"], vhod=t_in, vyhod=t_out, zakryto=int(time.time() * 1000))
                self.dobavit(z); log("ВЫХОД", sym, z["status"], z.get("R"))

    def dobavit(self, z):
        with self.jr.open("a") as f: f.write(json.dumps(z, ensure_ascii=False) + "\n")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--variant", default="BOUNCE1", choices=list(VARIANTY))
    ap.add_argument("--cikl", action="store_true"); ap.add_argument("--proverka", action="store_true"); a = ap.parse_args()
    if a.proverka:
        b = h1("BTCUSDT"); print("закрытых H1 BTC:", len(b), dt.datetime.utcfromtimestamp(b[-1][0] / 1000)); print("фандинг 3 сут:", fanding("BTCUSDT", b[-72][0], b[-1][0]))
        print("ПРОВЕРКА: OK" if len(b) >= 300 else "ПРОВЕРКА: FAIL"); return
    t = Ten(a.variant); log("эпоха", t.epoha, a.variant)
    while True:
        try: t.shag()
        except Exception as e: log("ошибка шага:", type(e).__name__, str(e)[:200])
        if not a.cikl: break
        log("пульс: жив"); time.sleep(3600 - time.time() % 3600 + 90)       # каждый час, через 90 с после закрытия бара

if __name__ == "__main__":
    main()
