# Crypto portfolio recovery plan — 2026-06-26

Цель: собрать проверяемый крипто-пакет стратегий с исследовательской целью `~60% годовых` после комиссий при минимуме красных месяцев. Это не обещание доходности; это критерий отбора и промоушена. Деньги получает только то, что прошло reproducible data → execution parity → monthly/WF → shadow → canary.

## Текущий факт live

На последнем proof-of-life сервер жив, открытых позиций нет. Ненулевой риск фактически остался только на `alt_resistance_fade_v1` / flat-short. `att1`, `range`, `breakdown` были остановлены монитором через `runtime/strategy_pause.env` из-за деградации последних сделок. `ivb1`, `midterm`, `elder`, `hzbo1` не имеют права на риск без новых gate-результатов.

Это не “бот запрещён торговать”; это fail-closed состояние после реальных минусов. Разблокировка — не включить всё обратно, а поднять только repaired sleeves через shadow/canary.

## Костяк, который собираем

| Sleeve | Роль в портфеле | Текущий статус | Следующее доказательство |
| --- | --- | --- | --- |
| `inplay_retest_v3` | ручная логика владельца: объёмная in-play монета, сильный уровень, ретест/отбой | исправлены entry ATR и sloped projection | bounded 24h sweep → monthly/WF |
| `impulse_volume_breakout_v1` / IVB1 | импульс → откат → продолжение | добавлены max entry distance, current ATR risk, min RR, hot-reload reset | next-open recheck, затем maker/fill-risk |
| `alt_inplay_breakdown_v1` | медвежий пробой поддержки + слабый ретест | добавлены min/max stop, min RR, trailing fields | bear-window entry-quality sweep |
| `pump_fade_smart_v1` / PFS1 | памп → exhaustion → rejection short | добавлены stop guards, funding timestamp safety, selector reset | strict package sweep with historical funding |
| `spike_fade_v3` | фейд пампа/дампа в реальный clustered level | stop geometry переведена на entry ATR | bounded 24h sweep |
| `alt_horizontal_break_v1` / HZBO1 | пробой горизонтальных зон | EMA gate уже исправлен | bounded cache-only sweep |
| `elder_triple_screen_v2` / ETS2 | канонический Elder 4h/1h/15m | добавлены actual RR/stop/entry distance guards | bounded canonical sweep |
| `btc_eth_midterm_*` | низкочастотная нога BTC/ETH | кандидат, но результат зависит от real exit model | execution-accurate monthly/WF, regime-side filter |
| funding/liquidation/basis | structural edge, сглаживатель | данные есть частично | отдельный server-only research после price sleeves |

## 24h research queue

Новый bounded config: `configs/research_priority_24h_20260626.json`.

Очередь запускает максимум один процесс одновременно (`nice=15`) и не трогает live configs. Порядок:

1. `ivb1_short_next_open_recheck_v1`
2. `breakdown_recent_bear_window_v2_entry_quality`
3. `pfs1_solo_24h_bounded_v1`
4. `spike_fade_v3_24h_bounded_v1`
5. `hzbo1_24h_bounded_v1`
6. `ets2_canonical_24h_bounded_v1`
7. `inplay_retest_v3_24h_bounded_v1`

Команда:

```bash
python3 scripts/run_nightly_research_queue.py --config configs/research_priority_24h_20260626.json
```

Статус:

```bash
cat runtime/research_priority_24h/status.json
tail -n 80 logs/research_priority_24h/*.log
```

## Promotion gates

Одна стратегия может попасть в shadow только если:

- backtest uses closed candles / next-open where live cannot fill close;
- PF >= 1.20 для первичного WATCH, PF >= 1.30 для GO;
- после costs и slippage expectancy > 0;
- trades >= 20 для bounded first pass, затем >= 60 или обоснованная низкая частота;
- max DD <= 8-10% на тестовом equity;
- negative month streak <= 2;
- top month contributes < 50% gross profit;
- no known live/backtest parity bug;
- strategy has min/max stop and min RR guards.

В canary деньги попадают только после shadow:

- shadow 3-7 дней без stale-data / duplicate order / missing stop;
- incident loop включён: если sleeve ловит серию стопов, отключается sleeve, не весь бот;
- live positions and broker/exchange stops reconcile cleanly.

## Как перестать терять недели

1. Любой новый research обязан иметь spec, status path и log path.
2. Heavy runners не запускаются рядом с live без `max_active_processes=1`, `nice`, cache-only или memory-safe режима.
3. Каждый день оператор смотрит один файл статуса, а не ищет screen руками.
4. Claude/DeepSeek могут предлагать идеи, но промоушен делает только gate с воспроизводимыми данными.
5. “Архив” означает `risk=0 until repaired`, а не удаление идеи. Классические логики сохраняем, но переписываем контракт исполнения.

## Tooling policy

- Optuna использовать для constrained optimization: PF/DD/monthly/trades/stability, не максимум PF.
- VectorBT использовать как быстрый pre-screen для идей, не как источник финального live-решения.
- NautilusTrader изучать для research-to-live parity, но не мигрировать live-монолит до стабилизации текущего бота.
- Freqtrade использовать как внешний benchmark идей и документации по crypto research, не как replacement.

## Ближайший выход к торговле

1. Сначала deploy этих safety/geometry патчей на сервер без рестарта live.
2. Запустить `research_priority_24h_20260626`.
3. Через сутки собрать `PASS/WATCH/CUT` по каждому sleeve.
4. Собрать портфельный replay из PASS/WATCH sleeves.
5. Если портфель проходит gates — включить shadow/risk=0.
6. Canary только после shadow: маленький риск, per-sleeve circuit breaker, без включения деградировавших старых параметров.

## 2026-06-26 server safety note

`package_pfs1_pump_fade_v1` нельзя автоматически гонять на live VPS 1GB: первый ряд занял ~506MB RSS рядом с live bot и оставил ~53MB available. Для live-хоста он заменён на `pfs1_solo_24h_bounded_v1`. Package additivity PFS1 остаётся нужной, но должна идти на research host или в memory-safe runner.
