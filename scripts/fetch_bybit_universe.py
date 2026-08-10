#!/usr/bin/env python3
"""СКАЧИВАНИЕ ДАННЫХ BYBIT — снимает главный блокер проекта.

    python3 scripts/fetch_bybit_universe.py --list-only
    python3 scripts/fetch_bybit_universe.py --top 150 --since 2023-01-01
    python3 scripts/fetch_bybit_universe.py --top 150 --since 2023-01-01 --resume

ЗАЧЕМ
  Три последние проверки упёрлись не в отсутствие эджа, а в объём выборки:
  9 сделок, 1 сделка, 5 сделок. На 13 монетах за два года потолок достигнут.
  При 150 символах те же тесты дают в 10 раз больше сделок, и вопросы,
  которые сегодня неразрешимы, становятся разрешимыми.

  Данные публичные, ключ не нужен. Частота запросов ограничена API, поэтому
  загрузчик делает паузу между страницами и повторяет временные ошибки.

ЧТО ДЕЛАЕТ
  1. Тянет список бессрочных USDT-контрактов Bybit.
  2. Для каждого ТЕКУЩЕГО контракта определяет дату листинга (`launchTime`).
     Это всё ещё survivor-only universe: публичный текущий endpoint не
     возвращает уже делистнутые контракты. Данные пригодны для discovery, но не
     для promotion-grade point-in-time проверки.
  3. Качает 5m свечи с указанной даты, страницами по 1000, с паузой.
  4. Пишет в data_cache/ в том же формате, что читает движок:
     [[ts_ms, o, h, l, c, v], ...]  — совместимо с существующим кэшем.
  5. `--resume` пропускает уже скачанные символы, поэтому обрыв не страшен.

ОБЪЁМ
  150 символов × 3 года 5m ≈ 47 млн баров ≈ 4-6 ГБ JSON.
  Время: при паузе 0.1 с между страницами — порядка 4-6 часов.
  Место проверяется перед стартом.

БЕЗОПАСНОСТЬ
  Только публичный GET /v5/market/*. Никаких ключей, ордеров и приватных
  эндпоинтов. Скрипт физически не может ничего купить или продать.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://api.bybit.com"
CACHE = Path("data_cache")
PAGE = 1000
BAR_MS = 300_000
PAUSE = 0.12
RETRIES = 4


def get(path: str, params: dict) -> dict:
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    last = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.loads(r.read().decode())
            if data.get("retCode") != 0:
                raise RuntimeError(f"retCode={data.get('retCode')} {data.get('retMsg')}")
            return data["result"]
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{path} не отвечает после {RETRIES} попыток: {last}")


def instruments() -> list[dict]:
    """Все бессрочные USDT-контракты с датой листинга."""
    out, cursor = [], ""
    while True:
        params = {"category": "linear", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        res = get("/v5/market/instruments-info", params)
        for it in res.get("list", []):
            if it.get("quoteCoin") != "USDT" or it.get("contractType") != "LinearPerpetual":
                continue
            if str(it.get("status", "")).lower() not in ("trading", ""):
                continue
            try:
                launch = int(it.get("launchTime") or 0)
            except (TypeError, ValueError):
                launch = 0
            out.append({"symbol": it["symbol"], "launch_ms": launch})
        cursor = res.get("nextPageCursor") or ""
        if not cursor:
            break
        time.sleep(PAUSE)
    return out


def turnover_rank() -> dict[str, float]:
    """Оборот за 24ч — для отбора топ-N. НЕ point-in-time: это сегодняшний
    срез, и отбор по нему вносит survivorship. Поэтому в кэш кладём ВСЕ
    символы с датами листинга, а ранг используется только для порядка
    скачивания, чтобы ликвидные приехали первыми."""
    res = get("/v5/market/tickers", {"category": "linear"})
    out = {}
    for t in res.get("list", []):
        try:
            out[t["symbol"]] = float(t.get("turnover24h") or 0)
        except (TypeError, ValueError):
            pass
    return out


def klines(symbol: str, start_ms: int, end_ms: int) -> list[list]:
    rows, cur = [], start_ms
    while cur <= end_ms:
        # Bybit returns newest-first. Bound every request to one PAGE-sized time
        # window so the response direction cannot collapse a multi-year fetch
        # into the latest 1000 candles.
        window_end = min(end_ms, cur + (PAGE - 1) * BAR_MS)
        res = get("/v5/market/kline", {
            "category": "linear", "symbol": symbol, "interval": "5",
            "start": cur, "end": window_end, "limit": PAGE,
        })
        page = res.get("list") or []
        if not page:
            break
        page = sorted(page, key=lambda x: int(x[0]))
        bounded = []
        for k in page:
            ts = int(k[0])
            if cur <= ts <= window_end:
                bounded.append(ts)
                rows.append([ts, float(k[1]), float(k[2]), float(k[3]),
                             float(k[4]), float(k[5])])
        if not bounded:
            raise RuntimeError(
                f"{symbol}: API page outside requested window {cur}..{window_end}"
            )
        nxt = max(bounded) + BAR_MS
        if nxt <= cur:
            break
        cur = nxt
        time.sleep(PAUSE)
    # дубли по метке времени убираем, порядок сохраняем
    seen, clean = set(), []
    for r in rows:
        if r[0] in seen:
            continue
        seen.add(r[0]); clean.append(r)
    return clean


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=150)
    ap.add_argument("--since", default="2023-01-01")
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--min-bars", type=int, default=20000,
                    help="не сохранять символы короче этого (мало данных = бесполезно)")
    a = ap.parse_args()

    since_ms = int(datetime.strptime(a.since, "%Y-%m-%d")
                   .replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(time.time() * 1000)

    print("тяну список инструментов...", flush=True)
    inst = instruments()
    print(f"бессрочных USDT-контрактов: {len(inst)}")

    CACHE.mkdir(exist_ok=True)
    meta_path = CACHE / "_bybit_listing_dates.json"
    meta_path.write_text(json.dumps(inst, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"даты листинга сохранены: {meta_path}")
    manifest_path = CACHE / "_bybit_universe_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_id": "bybit_current_survivor_universe_v1",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "source": "/v5/market/instruments-info",
                "scope": "current_trading_linear_perpetuals_only",
                "point_in_time_complete": False,
                "delisted_contracts_included": False,
                "intended_use": "research_discovery_not_capital_promotion",
                "symbol_count": len(inst),
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"ограничение universe сохранено: {manifest_path}")

    turn = turnover_rank()
    inst.sort(key=lambda x: -turn.get(x["symbol"], 0.0))
    picked = inst[: a.top]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "selection_as_of_utc": datetime.now(timezone.utc).isoformat(),
            "selection_rule": "current_24h_turnover_desc",
            "selection_is_point_in_time_safe": False,
            "selected_symbols": [it["symbol"] for it in picked],
            "selected_rows": [
                {
                    "symbol": it["symbol"],
                    "launch_ms": it["launch_ms"],
                    "turnover24h": turn.get(it["symbol"], 0.0),
                }
                for it in picked
            ],
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\nк скачиванию: {len(picked)} символов, 5m с {a.since}")
    print(f"{'символ':<16}{'листинг':>12}{'оборот 24ч, $':>16}")
    for it in picked[:15]:
        d = (datetime.fromtimestamp(it["launch_ms"] / 1000, timezone.utc).date()
             if it["launch_ms"] else "?")
        print(f"{it['symbol']:<16}{str(d):>12}{turn.get(it['symbol'], 0):>16,.0f}")
    if len(picked) > 15:
        print(f"... ещё {len(picked) - 15}")

    free_gb = shutil.disk_usage(".").free / 1e9
    est_gb = len(picked) * 0.035
    print(f"\nсвободно {free_gb:.1f} ГБ, оценка объёма {est_gb:.1f} ГБ")
    if free_gb < est_gb * 1.5:
        print("МАЛО МЕСТА — уменьши --top или освободи диск")
        return 1

    if a.list_only:
        print("\n--list-only: скачивание не запускалось")
        return 0

    ok = skipped = short = failed = 0
    t0 = time.time()
    for i, it in enumerate(picked, 1):
        sym = it["symbol"]
        start = max(since_ms, it["launch_ms"] or since_ms)
        existing = sorted(CACHE.glob(f"{sym}_5_*.json"))
        if a.resume and existing:
            skipped += 1
            continue
        try:
            rows = klines(sym, start, end_ms)
        except Exception as e:                        # noqa: BLE001
            print(f"[{i}/{len(picked)}] {sym}: ОШИБКА {e}", flush=True)
            failed += 1
            continue
        if len(rows) < a.min_bars:
            print(f"[{i}/{len(picked)}] {sym}: {len(rows)} баров — мало, пропуск", flush=True)
            short += 1
            continue
        out = CACHE / f"{sym}_5_{rows[0][0]}_{rows[-1][0] + BAR_MS}.json"
        out.write_text(json.dumps(rows), encoding="utf-8")
        ok += 1
        el = time.time() - t0
        eta = el / i * (len(picked) - i) / 60
        print(f"[{i}/{len(picked)}] {sym}: {len(rows)} баров -> {out.name}  "
              f"осталось ~{eta:.0f} мин", flush=True)

    print(f"\nготово: сохранено {ok}, пропущено {skipped}, коротких {short}, ошибок {failed}")
    print("проверить покрытие перед использованием:")
    print("    python3 scripts/audit_backtest_run.py <тег>   после первого прогона")
    print("    предполётная проверка покрытия есть в portfolio_13symbols.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
