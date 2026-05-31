# Deploy Day Checklist — Codex one-pager
*Когда Codex возвращается. Всё по порядку. Не пропускать шаги.*

---

## Pre-flight (5 минут)

```bash
cd /root/by-bot
git pull
git log --oneline | head -10               # убедиться что патчи Opus 2026-05-27 здесь
ls -la configs/autoresearch/package_*_v1.json  # 5 наших файлов должны быть
python3 scripts/validate_sweep_configs.py           # должно быть 0 errors; warnings по старым sweep допустимы
```

Если `validate_sweep_configs.py` показывает `failed > 0` — НЕ деплоить, спрашивать оператора.

---

## Block 0 — Размораживаем бота (10 минут)

```bash
# 0.1 Web фикс — useFetch null-safety уже в коде
supervisorctl restart web
curl -s http://localhost:8765/api/status | head    # должен ответить

# 0.2 Разморозить режим (заморожен с 3 апреля!)
python3 scripts/reset_regime_neutral.py
# Проверка: configs/regime_orchestrator_latest.env — свежий timestamp

# 0.3 Перезапустить бота
# СНАЧАЛА:  python3 -c "import json; print(json.load(open('runtime/positions.json'))['open_count'])"
# Только если open_count == 0:
supervisorctl restart bot
tail -50 logs/bot.log | grep -i error          # не должно быть критичных

# 0.4 Установить базовые cron'ы (раз и навсегда)
crontab -l > /tmp/cron.bak
cat >> /tmp/cron.bak << 'CRON'
0  */4 * * *  cd /root/by-bot && python3 bot/regime_orchestrator.py >> logs/regime_orchestrator.log 2>&1
0  */6 * * *  cd /root/by-bot && .venv/bin/python3 scripts/crypto_coin_screener.py --tg >> logs/screener.log 2>&1
0  2  * * 1   cd /root/by-bot && .venv/bin/python3 scripts/build_symbol_router.py >> logs/router.log 2>&1
CRON
crontab /tmp/cron.bak
crontab -l   # verify
```

---

## Block 1 — Self-healing infrastructure (5 минут)

```bash
# Добавить cron'ы Wave 2 (новые скрипты Opus):
crontab -l > /tmp/cron.bak
cat >> /tmp/cron.bak << 'CRON'
0    */4 * * *  cd /root/by-bot && python3 scripts/live_vs_backtest_monitor.py >> logs/strategy_monitor.log 2>&1
0    *   * * *  cd /root/by-bot && python3 scripts/validate_sweep_configs.py --tg >> logs/sweep_validate.log 2>&1
*/15 *   * * *  cd /root/by-bot && python3 scripts/regime_change_reopt.py --tg >> logs/regime_reopt.log 2>&1
*/5  *   * * *  cd /root/by-bot && python3 scripts/auto_dns_recovery.py --tg >> logs/dns_health.log 2>&1
30   6   * * *  cd /root/by-bot && python3 scripts/build_strategy_registry.py --drift --tg >> logs/registry.log 2>&1
0    9   * * *  cd /root/by-bot && python3 scripts/auto_apply_research_winner.py --dry-run --tg >> logs/auto_apply.log 2>&1
*/30 *   * * *  cd /root/by-bot && python3 scripts/run_research_queue_worker.py --tg >> logs/research_queue_worker.log 2>&1
CRON
crontab /tmp/cron.bak
```

Все скрипты безопасны (только TG-уведомления, никаких изменений в `.env` без `--apply`).

---

## Block 2 — Sweep queue (запускать ПОСЛЕДОВАТЕЛЬНО, между запусками проверять)

**Перед началом**: `git status` чистый, `python3 scripts/build_strategy_registry.py --drift` показывает 0-3 known issue.

```bash
# 2.1 ATT1 RSI relax — 36 комбо, ~2-3ч
nohup .venv/bin/python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/package_att1_rsi_relax_v1.json \
  > logs/sweep_att1.log 2>&1 &

# Дождаться завершения (tail -f logs/sweep_att1.log; завершён когда строка "Done. ..." в конце)
# Затем посмотреть ranked:
ls -t backtest_runs/ | grep autoresearch_.*att1_rsi_relax | head -1
head -5 backtest_runs/<вышел_dir>/ranked_results.csv

# Решение: если winner с PF>1.591, DD<7, trades>50 → запустить:
python3 scripts/auto_apply_research_winner.py --dry-run --strategy ATT1
# Прочитать предложение в TG. Если ОК — оператор делает manual apply.
```

Аналогично для остальных в порядке: BRC1 → ASC1 longs → ASB1 → Elder EMA.

**Правило**: следующий sweep запускается ТОЛЬКО когда предыдущий завершён + winner либо deployed либо отвергнут.

---

## Block 3 — Sub-account для арбитража (Codex договаривается с оператором)

**Делает оператор в Bybit UI** (Codex даёт инструкцию):
1. Account → Sub Accounts → Create Sub → тип "Unified Trading"
2. Имя: `arb-overlay`
3. Generate API Key с правами: spot trade ✓, derivatives trade ✓, withdrawal ✗
4. Whitelist IP сервера бота
5. Перевод капитала: оператор переводит $500-700 в sub (из main или с банка)

**Делает Codex**:
1. Получить ключи от оператора (НЕ коммитить в git!)
2. Обновить `.env`:
```env
BYBIT_ACCOUNTS_JSON=[
  {"name":"main", "key":"...", "secret":"...", "trade":{"enabled":true,"leverage":3,"risk_pct":0.01,...}},
  {"name":"arb_overlay","key":"NEW","secret":"NEW","trade":{"enabled":false,"leverage":1,"risk_pct":0.005,"max_positions":2,"min_notional_usd":50,"reserve_equity_frac":0.0}}
]
```
3. `trade.enabled=false` для sub в первую неделю — только логи, без ордеров.
4. Запустить funding sweep:
```bash
.venv/bin/python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/package_funding_harvest_v1.json
```

**Дальше**: 30 дней shadow на sub, потом ENABLE_FUNDING + RISK_MULT=0.05, дальше масштаб.

---

## Block 4 — Health checks (запускать каждый день первую неделю)

```bash
# Утром:
python3 scripts/build_strategy_registry.py --drift          # должно быть 0-3 known
python3 scripts/validate_sweep_configs.py                   # 0 errors; warnings допустимы
python3 scripts/live_vs_backtest_monitor.py --days 7        # пока пусто, ОК
cat runtime/strategy_health.json | python3 -m json.tool     # все ✅
cat runtime/dns_health.json | python3 -m json.tool          # healthy=true
python3 scripts/run_research_queue_worker.py --status       # сколько в очереди

# Логи:
tail -30 logs/bot.log | grep -iE "error|warning|fail"
tail -10 logs/strategy_monitor.log
tail -10 logs/regime_reopt.log
```

Telegram: ожидать ежедневное сообщение от `auto_apply_research_winner --dry-run --tg` в 9:00 UTC.

---

## ⛔ Что НЕ делать

- НЕ менять `.env` пока `open_trades > 0`
- НЕ запускать `auto_apply_research_winner.py --apply-approved` без явного "да" от оператора
- НЕ менять `RISK_PER_TRADE_PCT`, `BYBIT_LEVERAGE`, `ORCH_GLOBAL_RISK_MULT` через автомат
- НЕ деплоить sweep winner с PF < 1.591
- НЕ запускать 2 sweep одновременно (CPU перегрузка, неконкурентные fee assumptions)
- НЕ оставлять sub `arb_overlay` с `enabled=true` без 30d shadow

---

## Контакты / эскалация

При проблемах:
1. `runtime/dns_health.json` → если broken: `sudo python3 scripts/auto_dns_recovery.py --apply`
2. `runtime/strategy_health.json` → если degraded: проверить `runtime/auto_apply_log.jsonl`
3. Sweep падает → `python3 scripts/validate_sweep_configs.py --file <path> --strict`
4. Бот падает при старте → `python3 -c "import smart_pump_reversal_bot"` для AST/import чек

Все 3 финальных документа Opus читать в порядке:
1. `OPUS_AUDIT_2026_05_27.md` — что было сломано и как починено
2. `OPUS_ROADMAP_2026_05_27.md` — план развития 4 волны
3. `OPUS_ARBITRAGE_HONEST_2026_05_28.md` — реальные цифры по арбитражу
4. `OPUS_ARBITRAGE_PLAN_2026_05_27.md` — план депозитов и sub-аккаунтов

И этот файл — на каждый деплой день.
