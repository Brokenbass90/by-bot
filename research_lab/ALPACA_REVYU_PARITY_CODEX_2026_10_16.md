# Независимое ревью Alpaca parity (Claude, 16.10.2026, только чтение)

Объект: recovery `05d77bf` (Codex), отчёт `ALPACA_BASELINE_PARITY_CANDIDATE_2026_10_16.md`. Эталон: research `981b62f` + recovery `2e68b1f`.

**OFFLINE_BASELINE_COMPONENT_PARITY: PASS (подтверждено независимо).**
- `git archive 05d77bf` в чистую копию; эталонные ETALON/sdelki взяты из МОЕГО коммита 981b62f, не из копии Codex.
- `PYTHONHASHSEED=0 replay_alpaca_baseline_parity_v1.py` → 24 отбора exact, 66 начальных стопов, 695/637 дневных
  состояний (≤1e-9), 56 стоп-выходов, ядро сделок 64/64 `2347a7ec606cd845`.
- Кандидат `alpaca_strategy_parity_v1.py` (sha d87f5e07…) реализует храповик САМ (daily_transition, стр. 194–198:
  HWM по close, активация 3.5 %, max(stop, HWM·0.965, entry·1.005), потолок close·(1−10 бп), стоп только вверх);
  с эталоном общие только `quantize_sell_stop` и замороженный отборщик — совпадение не тавтологично.
- TTL в `alpaca_dynamic_v1.py`: ранжир вне своего окна → `NO_SEND / STALE_SIGNAL_RESELECT_FAIL`; сохранённые
  Oct9→Oct15 входные данные отклоняются.

**ALPACA_STRATEGY_PARITY (развёрнутая): BLOCKED** — согласен с Codex, три названных расхождения:
1. ритм: LIVE = Dynamic weekly (одобрен владельцем 06.10), эталон = monthly. Выбор — за владельцем; weekly без своего
   prereg/бэктеста не является проверенной стратегией (BRIEF §5: недельная ротация закрыта как хуже).
2. менеджер: LIVE поднимает стоп внутри дня (5 мин), эталон — по закрытию сессии; кандидат дневного менеджера есть,
   но не привязан к продакшену.
3. источник дневного закрытия/календаря для живого менеджера не привязан (replay использует логические часы OHLC).

Классификация прошлых intents принята: NET PAPER 12–13.10 = OPERATIONAL_VALIDATION; NET LIVE 15.10 =
OFF_PROTOCOL_STALE_SIGNAL (+RISK_REFERENCE); CRWD/AMD/META 01.10 — вход 14:10 вместо открытия 13:30, AMD/META
стоп на 1 цент выше эталона → не ON_PROTOCOL; остальное UNKNOWN (нет родословной отбора/ATR). Доказательств edge
из LIVE/PAPER Alpaca на сегодня нет ни «за», ни «против».
