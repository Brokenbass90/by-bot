# Codex Task: Router Quality Fixes

## Проблема
Роутер переходит в `degraded_fallback` при сетевых ошибках и:
1. Отдаёт мемкоины (FARTCOIN, TAOUSDT) в allowlists без фильтрации
2. Geometry scoring не работает (all 0.5)
3. Нет backtest gate
4. IVB1 получает пустой список в bear_chop, не ясно получает ли в bull_chop

---

## Fix 1: Убрать мемкоины из fallback списков

В `scripts/build_symbol_router.py` или `scripts/dynamic_allowlist.py` найти
список DENYLIST для fallback режима и добавить:

```python
MEME_DENYLIST = {
    "FARTCOINUSDT", "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "BONKUSDT",
    "FLOKIUSDT", "BOMEUSDT", "WIFUSDT", "MEMEUSDT", "NEIROUSDT",
    "1000SATSUSDT", "ORDIUSDT",
}
```

Применить к fallback selection:
```python
safe_symbols = [s for s in fallback_symbols if s not in MEME_DENYLIST]
```

Это мгновенно убирает самые волатильные монеты из fallback без изменения
основной логики скана.

Исключение для breakdown стратегий: DOGEUSDT можно оставить (ликвидный,
умеренная волатильность), но FARTCOIN/TAOUSDT — нет.

---

## Fix 2: Проверить IVB1 allowlist на сервере

Выполнить SSH команду:
```bash
cat runtime/router/symbol_router_state.json | python3 -c "
import json, sys
state = json.load(sys.stdin)
ivb1 = state.get('profiles', {}).get('IVB1_SYMBOL_ALLOWLIST', {})
print('IVB1 symbols:', ivb1.get('symbols'))
print('IVB1 source:', ivb1.get('source'))
print('Regime:', state.get('regime'))
print('scan_ok:', state.get('scan_ok'))
"
```

Если IVB1 symbols пустые на сервере тоже — добавить anchor_symbols для IVB1
в profile registry для bull_chop режима.

В `configs/strategy_profile_registry.json` найти профиль ivb1 для bull_chop
и добавить anchor symbols:
```json
{
  "profile_id": "ivb1_bull_chop",
  "regimes": ["bull_chop"],
  "anchor_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
  "min_symbols": 2,
  "max_symbols": 5
}
```

---

## Fix 3: Добавить алерт при degraded_fallback

В `scripts/build_symbol_router.py` в конце main() если status == degraded_fallback:

```python
if state.get("degraded"):
    tg_token = os.getenv("TG_TOKEN", "")
    tg_chat = os.getenv("TG_CHAT_ID", "")
    if tg_token and tg_chat:
        _tg_send(tg_token, tg_chat,
            f"⚠️ Router DEGRADED: scan_ok=False\n"
            f"Error: {state.get('scan_error', '')[:200]}\n"
            f"Using fallback symbols — check API connectivity"
        )
```

Сейчас деградация происходит молча. После этого в Telegram будет алерт.

---

## Fix 4: Backtest gate — минимальная версия

В `configs/strategy_profile_registry.json` для каждого профиля добавить
`pnl_min_threshold` (минимальный PnL монеты за последние 90 дней на данной
стратегии). Если backtest performance CSV доступен — фильтровать монеты ниже
порога.

Это не срочно, реализовать после Fix 1-3.

---

## Fix 5: Проверить geometry data pipeline

```bash
# На сервере:
ls -la runtime/geometry/ 2>/dev/null || echo "no geometry dir"
cat runtime/geometry/geometry_state.json 2>/dev/null | python3 -c "
import json, sys
g = json.load(sys.stdin)
symbols = list(g.keys())[:5]
print('symbols with geometry:', len(g), 'first 5:', symbols)
" 2>/dev/null || echo "no geometry state"
```

Если geometry_state.json пустой или содержит 0 монет — geometry scoring
работает с нулевыми данными и все scores = 0.5.

Исправить: убедиться что `scripts/build_geometry_state.py` запускается
в crontab и что он успешно заполняет runtime/geometry/.

---

## Приоритет:
1. Fix 1 (meme denylist) — 30 минут, СРОЧНО
2. Fix 2 (IVB1 allowlist проверка) — 15 минут
3. Fix 3 (TG алерт) — 30 минут
4. Fix 5 (geometry проверка) — 1 час
5. Fix 4 (backtest gate) — 3-4 часа, не срочно
