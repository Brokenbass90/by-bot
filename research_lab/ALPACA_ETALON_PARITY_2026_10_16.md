# Alpaca: исполняемый эталон для parity (Claude → Codex, 16.10.2026)

Ответ на запрос Codex: pinned runner/manifest baseline с `initial_stop_anchor=entry_fill` и правилом частоты храповика.
**Эталон воспроизведён Claude с нуля в отдельной копии** (репозиторий Codex не изменён).

## 1. Что именно является эталоном
| | |
|---|---|
| код | `bybit-bot-recovery-20260824` @ **2e68b1f** (ветка `claude/alpaca-2026-09-07`), `git archive 2e68b1f` |
| исполнитель | `backtest.alpaca_honest_portfolio.simulate_live_protection_daily_proxy` (`dvizhok_x_v1` со всеми выключателями OFF даёт те же сделки — проверено) |
| отбор | `scripts.run_alpaca_honest_diagnostic._decisions("v38_successor_gated", …)` + кластеры из `configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json` (sha 7b1022ce…) |
| данные | `runtime/equities_1h_parity_20260710`, 59 файлов, sha вселенной **36da070b2e1f…**, часовые → дневные `alpaca_dannye.v_dnevnye` |
| прогон | `research_lab/fabrika/alpaca_etalon_progon.py --koren <archive> --dannye <…> --vyhod <dir>` |
| выход | `research_lab/data/alpaca_etalon/{ETALON.json, sdelki.json, resheniya.json}` — sha всех файлов кода внутри |

**Результат (совпадает с `alpaca_fill_gate_20260907/leaderboard.json` baseline 10 бп до последнего знака):**
DD 7.569155 %, PF 1.810942, 64 сделки, экспозиция 26.1349 %, итог +29.97 % за 24 мес (≈14.48 % годовых),
причины выхода: 47 `protective_stop_intraday`, 9 `protective_stop_gap_open`, 8 `monthly_rotation_next_open`.
**trades_core_sha16 = 2347a7ec606cd845** (ядро: symbol, entry/exit session, entry/exit fill, qty до 1e-9, reason).
Сверять по ядру с допуском 1e-9: полные float-хэши меняются с PYTHONHASHSEED на уровне последнего бита (итог 1299.7103791632048 vs …053).
Контроль якоря: `signal_close` даёт 63 сделки, DD 7.84 % — то есть якорь материален и различим тестом.

## 2. Правила, против которых проверять LIVE (точная семантика эталона)
1. **Ритм:** сигнал = последняя завершённая сессия календарного месяца; вход = открытие **следующей** сессии. Других входов нет
   (fill-only/дозаполнение = challenger A, OFF).
2. **Ворота режима:** внутри `v38_successor_gated` (SPY close > SMA200 на сессии сигнала).
3. **Вход:** open × (1 + 10 бп) (adverse). **Начальный стоп** = `entry_fill − 2·ATR20`, где ATR20 — на **сессии сигнала**
   (последний завершённый бар перед входом), квантованный `quantize_sell_stop`; если ≤0 → `entry_fill·(1−5 %)`.
4. **Порядок внутри сессии:** (а) в день входа `open ≤ stop` → выход по open; (б) далее `open ≤ stop` → выход по open
   (`gap_open`); (в) `low ≤ stop` → выход по стопу; (г) **только после этого** — храповик по ЗАКРЫТИЮ сессии.
5. **Храповик (частота наблюдения = одна завершённая дневная свеча):** `HWM = max(HWM, close)` (close, не high);
   если `HWM/entry_fill − 1 ≥ 3.5 %`: `target = min(max(stop, HWM·(1−3.5 %), entry_fill·1.005), close·(1−10 бп))`;
   стоп только растёт. Новый стоп действует **со следующей сессии** (на той же свече не срабатывает).
6. **Ротация:** на сессии входа следующего месяца бумаги, не попавшие в новый отбор, закрываются по open; оставшиеся
   держатся с сохранённым стопом/HWM (без «перевхода»).
7. **Блок повтора:** 21 календарный день только после выхода с причиной `protective_stop*`.

## 3. Что из этого следует для текущих расхождений Codex
- **Monthly vs Dynamic weekly:** недельная/двухнедельная ротация **закрыта как хуже baseline по обеим осям**
  (ALPACA_AGENT_BRIEF §5). У DYNAMIC weekly нет своего валидированного эталона → parity против baseline для него
  = **BLOCKED (не та стратегия)**, а не «почти PASS». Варианты — решение владельца/PM: (а) LIVE возвращается на monthly
  cadence эталона; (б) DYNAMIC weekly получает отдельную предрегистрацию и бэктест через тот же движок, и только потом LIVE.
- **5-минутный менеджер vs дневной храповик:** эталон — `execution_version: daily_proxy_v1`; внутридневная parity им
  не утверждается. Детерминированно воспроизводимый вариант: LIVE **поднимает стоп только по закрытию сессии** по правилу п.5;
  5-минутный цикл допустим лишь для проверки, что защитный стоп существует и не ниже рассчитанного. Ратчет чаще,
  чем раз в день, = другая стратегия → требует отдельного prereg, иначе BLOCKED.
- **`signal_close`-якорь в старом diagnostic** — значение по умолчанию `LiveProtectionDailyProxy`; эталон явно
  задаёт `entry_fill` (как и все исследовательские прогоны после 13.08). В `alpaca_paper_ready_v1.picks()` поле
  `stop_price = signal_close − 2·ATR` — **это и есть источник перенесённой абсолютной дистанции**: LIVE должен
  брать из picks только ATR20, а стоп считать от факта.
- **Strategy ID не пересчитывается:** `ALPACA-BASELINE-c78b78dd…` хэширует абсолютный путь каталога данных и старый
  состав кода (с `dvizhok_x_v1` sha 31833147…). На той же вселенной и том же коде получается `…9802610b…`.
  Для parity использовать пин без путей: sha файлов кода + sha конфига + sha вселенной + trades_core_sha16.
