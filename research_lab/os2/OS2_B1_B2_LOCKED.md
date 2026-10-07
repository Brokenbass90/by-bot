# КОНТРОЛЬНАЯ ТОЧКА: OS2_B1_B2_LOCKED — 07.10.2026 (Claude)

**Статус: LOCKED** (B1 ядро + B2 режим заморожены, replay исполним и покрыт тестами), с одним существенным открытием по окну проверки.

| пункт задания | результат | файл |
|---|---|---|
| 1. Реестр ядра 10–15 ног | 14 ног: механизм/сторона/ТФ/режим/доказательства/издержки/исполнение/статус/блокер | os2/YADRO_REESTR.md |
| 2. Аудит модулей | 20 модулей управления — 133 теста PASS; что LIVE / что код; карта соединений | os2/INVENTAR_SISTEM.md |
| 3. Режим без PnL | 4 существующих определения, критерии записаны ДО расчёта; выбран **D2 = bot/regime_orchestrator.compute_regime** (BULL/BEAR/NEUTRAL, 4h) — прошёл K1–K4, задержка 88 ч vs 104 у HMM; D1 EMA200 и D3 build_regime_state не прошли по «пиле» (78% / 58%) | os2/B2_KRITERII_REZHIMA.md, os2/B2_REZHIM_SRAVNENIE.json, os2/rezhim_v1.py, os2/REZHIM_V1_ZAMOK.json |
| 4. Исполняемый replay | os2/replay.py на существующем роутере strategy_priority_router; 4 теста (равенство рук, слоты/символ, режим режет, замок окна) + 4 теста режима | os2/test_replay.py, os2/test_rezhim_v1.py |
| 5. План WF + окно | ТЗ B3 зафиксировано; **окно 2025-10…2026-08 НЕ нетронуто** — печать потрачена 03.09 именно на ATT1(флет−)/SBR1(флет+) → финальное независимое окно переносится на SEALED_V2 с 2026-08-12 + тень вперёд | os2/B3_TZ.md, prereg/SEAL_SPENT.json |
| 6. Что старое берём без переписывания | роутер, гейты, exposure_gate, breakers, decision_bus, edge_monitor, champion_challenger, wf_folds, regime_orchestrator | os2/INVENTAR_SISTEM.md |

## Доказанные ошибки данных (исправлены в обвязке, стратегии не тронуты)
- Elder ETS2 и SF3 просят 15m; на H1 склад честно отказывает → 0 сделок. Августовские потоки ETS2/SF3 были посчитаны сломанным прибором. В B3 — на m5.
- replay: роутер считает время в секундах — исправлено в обвязке, покрыто тестом.

## Воспроизведение
    python3 research_lab/os2/rezhim_sravnenie.py      # B2 метрики (только < 2025-10-01)
    python3 research_lab/os2/rezhim_v1.py             # проверка замка: PASS
    python3 -m pytest -q -p no:cacheprovider -c /dev/null research_lab/os2/   # 8 PASS

## Следующие шаги Codex (по порядку, после Alpaca P0 и KITY 08–09)
1. Проверить deepseek_operator / deepseek_action_executor: может ли менять .env, риск, стратегии без GO. Если да — заблокировать флагом, отчёт.
2. Сверить живую метку режима: compute_regime на тех же закрытых 4h-барах BTCUSDT, что os2/rezhim_v1.py → одинаковые состояния (паритет).
3. Прогнать test_sleeve_breaker_generic и тесты живых гейтов в своей среде.
4. Минимальный план интеграции (не новый фреймворк): ноги → StrategyCandidate → rank_candidates → strategy_regime_gate; decision_bus в тени.
   Включать только после B3 PASS, сначала orders-OFF/PAPER, LIVE — GO владельца.

## 07.10 днём: подготовка B3 (к OS2_B3_READY)
- ETS2/SF3: 15m-данные из m5 (137 монет, os2/dannye_15m + MANIFEST sha), signaly переписан (база/удержание в часах/пауза ×5/база); проба SOL: ETS2 695, SF3 100 сделок.
- BOUNCE1: адаптер = AltSupportBounceV1Strategy через тот же интерфейс maybe_signal (логика не тронута), BTC/ETH как в PASS 02.08, стоп стратегии (×1.0), удержание 48 ч = time_stop 576×5m.
- wf.py + B3_KONFIG.json (sha 9b65e28c…) заморожены; тесты os2/: 12 PASS.
- Реестр загрязнения SEALED_V2: os2/ZAGRYAZNENIE_SEALED_V2.md — окно годно для вопроса маршрутизации.
