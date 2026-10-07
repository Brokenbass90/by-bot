# Передача Codex — OS2 (вечер 07.10). Порядок: после Alpaca P0; KITY 08–09.10 прерывает всё.

## Что из OS2 готово к интеграции, а что research-only
| часть | статус | файл |
|---|---|---|
| REZHIM_V1 = bot/regime_orchestrator.compute_regime (живой код, параметры по умолчанию) | ГОТОВО (замок, тесты) | research_lab/os2/rezhim_v1.py, REZHIM_V1_ZAMOK.json |
| replay на bot/strategy_priority_router | research-only (историческая проверка) | os2/replay.py, test_replay.py |
| политика маршрутизации | НЕТ — появится только после B3 PASS | os2/B3_KONFIG.json |

## Задачи Codex
1. **Аудит полномочий DeepSeek**: deepseek_operator (по умолчанию ON, API OFF), deepseek_action_executor, deepseek_autoresearch_agent —
   могут ли менять .env / риск / стратегии / LIVE-конфиг без GO владельца. Если да — заблокировать флагом без остановки торгового контура; отчёт.
2. **Паритет режима**: на одних и тех же закрытых 4h-барах BTCUSDT живой путь (runtime/regime.json, если используется) и
   os2/rezhim_v1.metki дают одинаковые состояния. Расхождение → описать (какие бары, почему).
3. **Тесты, требующие живого бота** (в research-VM не собираются): tests/test_sleeve_breaker_generic.py и гейты strategy_regime_gate/regime_side_gate в боевой среде.
4. **Минимальный план интеграции** (не новый фреймворк): живые ноги → StrategyCandidate → rank_candidates → strategy_regime_gate; decision_bus — в тени.
   Включение — только после B3 PASS: сначала orders-OFF/PAPER, LIVE — GO владельца.
