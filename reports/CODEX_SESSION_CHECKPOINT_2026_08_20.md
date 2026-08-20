# Codex session checkpoint — 2026-08-20

## Итог

Проект движется, но стадия остаётся **recovery + verified research**, а не
готовая много-ножевая торговая станция. Bybit live жив; второй crypto money
sleeve не разрешён. Alpaca — защищённый SAFE_HOLD pilot. MT5 manual-signal
контур безопасно подготовлен, но заблокирован до ротации утёкшего локального
MCP token. Web position console принят и проверен.

## Прямая live-проверка

- VPS: `bybot.service=active`, `trading-journal-web.service=active`.
- Bybit signed broker GET: `retCode=0`, открытых позиций `0`.
- `runtime/bot_heartbeat.json`: age около 14 секунд, `trade_on=true`,
  `dry_run=false`, `open_trades=0`, `regime=bull_trend`, WS guard inactive.
- Alpaca broker GET: equity `$490.13`, cash/BP `$391.47`, позиции ABBV и SCHW,
  нереализованный PnL около `+$7.81`, broker stop coverage `2/2`.
- Alpaca entry authority остаётся выключенной:
  `ALPACA_SEND_ORDERS=0`, `ALPACA_ALLOW_NEW_ENTRIES=0`.

Это snapshot, не вечная истина; перед любым live-изменением проверяется заново.

## Принято и проверено

### Web

Commit `37d50a8` принят: multi-position broker-truth console, видимый timeframe,
stale/conflict handling и безопасная отрисовка. Focused web tests: `28 passed`.
Полное встраивание standalone page в основной SPA ещё не завершено.

### MT5 manual-signal contour

Commits `4e41339`, `a3c04c5`, `0487b6c` сохранены локально. Контур:

`Telegram/web text -> deterministic parser -> fresh quote/stale guard -> risk
calculation -> account allowlist -> owner confirmation -> one-use token ->
execution -> broker reconciliation -> journal`.

Fail-closed восстановлен: execution default OFF, live нельзя включить env-флагом,
account allowlist пуст по умолчанию, direct close/BE endpoints выключены, journal
не считает исчезнувшую позицию закрытой без broker history. Seven direct safety
scripts PASS. `.env` mode `600`, нового token в нём пока нет.

Пример EURUSD корректно разбирается. При midpoint `1.16830` RR целей примерно:
TP1 `0.72R`, TP2 `1.06R`, TP3 `1.41R`, TP4 `2.56R`. Перед demo нужен фиксированный
exit-policy на канал; иначе отчёт поставщика и реальное исполнение будут разными.

### ATT1/SBR1 parity

Старая research-геометрия признана неэквивалентной live: research умножал уже
готовый стоп и сохранял старые цели; live строит широкий ATR stop и новые цели.
Выбран новый live-native contract; прежний PnL не даёт promotion authority.

Добавлены:

- `research_lab/adapter_parity.py` — fail-closed comparator normalized ledgers;
- `research_lab/prereg/PREREG_ATT1_SBR1_ADAPTER_PARITY_2026_08_20.md`;
- `tests/test_adapter_parity.py`.

Gate сравнивает data/config/source hashes, evaluation coverage, entry/SL/TP,
TP/runner fractions, time stop, cooldown, regime/drop reasons и deterministic
outcome/net R. Focused ATT1/SBR1/parity suite: `37 passed`.

Отдельный найденный стык: после фактического fill fixed TP/SL могут быть
восстановлены относительно fill, но runner targets пока остаются абсолютными.
Это должно войти в live-adapter ledger и не позволяет считать старый replay
эквивалентным исполнению.

## Research continuity

Живы 12 изолированных screen jobs. Материальные состояния:

- Inplay startup parity PASS: pre-sealed slices `32/40/62/81` raw signals;
  prospective ETH после старта пока `N=0`, orders/risk authority отсутствуют.
- ATT1 limit paper: `N=3`, maker fills `2/3`, mean saving `+2.48 bps`; это
  позитивный механизм, но выборка не разрешает live.
- Wide Bybit M5 materialization: 28/137 symbol directories, около 353 MiB;
  процесс продолжает загрузку, sealed holdout не читается.
- XSEC v3 shadow обновляется ежедневно, orders sent false.
- Funding shadow: 34–36 closed trials в текущих frozen summaries. Средние
  положительные, но одна версия имеет отрицательную медиану и до 89% positive
  concentration; promotion запрещён до tail/concentration audit.
- L2/tape ONDO свежий, public-only, storage guard разрешает запись; отдельные
  дни с coverage около 86% помечены и не могут считаться полными.

## Что НЕ готово

- Денежная crypto-книга: только ATT1 tiny canary. SBR1 — research candidate,
  не подключён к monolith; Inplay prospective N0; XSEC/funding shadow only.
- `bot/exposure_gate.py` имеет тесты, но не подключён к monolith.
- `regime_orchestrator.py` существует, но не реализует согласованный H1
  BTC/EMA200 flat-up/flat-down contract для ATT1/SBR1.
- Decision bus у ATT1 default OFF; SBR1 wiring отсутствует.
- Alpaca entry-relative challenger: proxy `25.65% annualized`, DD `14.36%`,
  40 trades, audit arithmetic PASS, но exact live contract false и PIT/corporate
  actions/paper lifecycle gates не закрыты.
- XAU: данные готовы (87,439 M5; 7,291 H1, pre-holdout), доказанной стратегии нет.
- FX/CFD: money authority отсутствует; сначала XAU frozen replay, затем
  portability на EURUSD/GBPUSD и broker-cost calibration.

## Следующий порядок

1. Реальные research/live emitters для normalized parity ledger; исправить
   fill/runner target rebasing и добиться comparator PASS.
2. Перепрогнать ATT1 short flat-down и SBR1 long flat-up на выбранной
   live-native геометрии, одинаковых издержках и pre-sealed bytes.
3. Подключить exposure gate и H1 EMA200 regime labels только в zero-risk shadow;
   затем повторить portfolio allocator replay.
4. Alpaca: exact paper lifecycle replay entry-relative challenger. До PASS
   SAFE_HOLD не снимается.
5. XAU: одна frozen session breakout/retest base/stress; news blackout —
   отдельный challenger, не подгонка основной руки.
6. MT5: owner rotates token, заполняет explicit account allowlist; затем один
   demo signal и reconciliation. Никаких реальных денег на первом запуске.
7. Завершить wide M5, затем Inplay multi-symbol replay без изменения frozen ETH
   prospective contract.

## Условные сроки, не обещания

- 1–2 engineering days: parity emitters + corrected ATT1/SBR1 rerun.
- 2–4 engineering days: Alpaca paper lifecycle parity и XAU first frozen replay.
- 1–2 weeks: решение о bounded Alpaca micro-canary, только если paper PASS.
- 3–6 weeks: возможный второй crypto money sleeve после parity, shadow и owner gate.
- 6–12 weeks: агрессивный сценарий 3–4 crypto legs; отрицательные результаты
  могут увеличить срок, поэтому дата не заменяет gates.

## Git/security blocker

Локальный safe HEAD: `0487b6c` плюс текущий parity checkpoint commit. Remote
ветка содержит старый commit с MT5 token и расходится с safe history. Сначала
token rotation, затем требуется отдельное явное разрешение владельца на
`git push --force-with-lease`. Обычный push сейчас не подходит.

В грязном worktree остаются сотни файлов Claude/legacy. Они не удалены и не
попали в тематические commits. Владение зонами закреплено в
`docs/ACTIVE_WORK_OWNERSHIP.md`.
