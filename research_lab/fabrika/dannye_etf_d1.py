#!/usr/bin/env python3
"""dannye_etf_d1.py — дневные бары ETF (Alpaca data, paper-ключ из configs/alpaca_paper_local.env, не печатается).
Только чтение рыночных данных, без ордеров. adjustment=all (дивиденды/сплиты — нужна полная доходность облигаций).
Кладёт data/etf_d1/<SYM>.json = [[YYYY-MM-DD, close_adj], ...]. До заморозки prereg доходности не считаются.
    python3 research_lab/fabrika/dannye_etf_d1.py
"""
import datetime as dt, json, sys, urllib.parse
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent
sys.path.insert(0, str(ROOT / "scripts"))
import materialize_alpaca_pit_daily as M

SIM = ["TLT", "IEF", "AGG", "SPY", "QQQ", "DIA"]
OUT = LAB / "data" / "etf_d1"


def main():
    e = M._load_env(ROOT / "configs/alpaca_paper_local.env")
    k, s = e.get("ALPACA_API_KEY_ID", ""), e.get("ALPACA_API_SECRET_KEY", "")
    if not k or not s:
        sys.exit("нет ключа Alpaca paper")
    h = M._alpaca_headers(k, s); OUT.mkdir(parents=True, exist_ok=True)
    for feed in ("sip", "iex"):
        rez, token, ok = {}, "", True
        try:
            while True:
                p = {"symbols": ",".join(SIM), "timeframe": "1Day", "start": "2015-12-01", "end": (dt.date.today() - dt.timedelta(days=2)).isoformat(),   # SIP: свежие 15 мин запрещены тарифом — конец позавчера
                     "limit": 10000, "adjustment": "all", "feed": feed, "sort": "asc"}
                if token:
                    p["page_token"] = token
                x = M._json_get(f"{M.ALPACA_DATA_ROOT}/v2/stocks/bars?{urllib.parse.urlencode(p)}", h)
                for sym, bars in (x.get("bars") or {}).items():
                    rez.setdefault(sym, {}).update({b["t"][:10]: float(b["c"]) for b in bars or []})
                token = str(x.get("next_page_token") or "")
                if not token:
                    break
        except Exception as ex:
            print(f"feed={feed}: {type(ex).__name__} {str(ex)[:150]}"); ok = False
        if ok and rez:
            for sym, d in rez.items():
                (OUT / f"{sym}.json").write_text(json.dumps(dict(feed=feed, bary=[[t, d[t]] for t in sorted(d)])))
                print(f"{sym} ({feed}): {len(d)} баров, {min(d)} … {max(d)}")
            return
    sys.exit("бары не получены ни по sip, ни по iex")


if __name__ == "__main__":
    main()
