"""Когда публикуется архив сделок Bybit за день? Для Bybit-нативной KITY признак дня d−1 нужен до входа в закрытие дня d.
Печатает HTTP Last-Modified файлов за последние 5 дней для BTC/SOL/WLD (только заголовки, без загрузки)."""
import datetime as dt, urllib.request
U = "https://public.bybit.com/trading/{s}/{s}{d}.csv.gz"
seg = dt.datetime.now(dt.timezone.utc).date()
for s in ("BTCUSDT", "SOLUSDT", "WLDUSDT"):
    for k in range(1, 6):
        d = (seg - dt.timedelta(days=k)).isoformat()
        try:
            r = urllib.request.urlopen(urllib.request.Request(U.format(s=s, d=d), method="HEAD", headers={"User-Agent": "research-paper"}), timeout=30)
            lm = r.headers.get("Last-Modified")
            t = dt.datetime.strptime(lm, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=dt.timezone.utc)
            konec = dt.datetime.fromisoformat(d).replace(tzinfo=dt.timezone.utc) + dt.timedelta(days=1)
            print(s, d, "опубликован", t.isoformat(), "через", round((t - konec).total_seconds() / 3600, 2), "ч после конца дня")
        except Exception as e:
            print(s, d, "нет/ошибка", type(e).__name__, str(e)[:80])
