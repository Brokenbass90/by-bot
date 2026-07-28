# Приёмка пакета Claude — 2026-07-28

Статус: `PARTIAL_ACCEPT / EVIDENCE_REBUILT`
Live risk, ATT1 signal/universe и реальные ордера не менялись.

## Что принято и уже реализовано

1. **Учёт размера поиска.** Новые autoresearch sweep сохраняют planned,
   scheduled и actually evaluated trial counts в candidate receipt, summary и
   ranked results. `n_trials_effective_independent` остаётся `null`, пока оно
   не измерено: соседние параметры нельзя выдавать за независимые опыты.
2. **Significance toolkit.** `research_lab/significance.py` принят после
   исправления ошибки `n_trials=1` и добавления тестов. DSR и power пока
   advisory: жёсткий gate нельзя включать с выдуманным числом независимых
   попыток или с effect size, подсмотренным у победителя.
3. **XSEC family-first gate.** Проведён preregistered landscape на 36
   конфигурациях. `36/36` положительны, median `+35.86%`; PIT rebuild
   оправдан. Это не capital PASS из-за survivor-only universe и исполнения.
4. **Regime split.** Принят как обязательная дешёвая диагностика до дорогого
   конвейера. Он уже отделил режимную short-beta от переносимых идей.
5. **Research station WIP.** Полезные per-trial IS/FWD/OOS metrics приняты.
   Выбор station-файла ограничен безопасным basename, чтобы новый launcher не
   превратился в произвольный path runner.

## Что принято как гипотеза, но не как PASS

### BOUNCE1, ошибочно названный ASB1

Claude тестировал `alt_support_bounce_v1` (`BOUNCE1`), а не live
`alt_slope_break_v1` (`ASB1`). Арифметика части прогонов воспроизводится, но:

- 292 строки содержали 278 уникальных сделок;
- 46-trade cross-symbol sample недостаточно мощный;
- `BOUNCE1_RISK_MULT=0` не создаёт виртуальные закрытия в текущем live path;
- TP fraction `0.0` фактически clamp-ится;
- sighting scripts наследуют ambient env и не имеют полного effective SHA.

Verdict: `REHABILITATE`, следующий gate — отдельный virtual
decision/fill/exit ledger и untouched prereg. В money sleeve не включён.

### Alpaca

Claude правильно требовал не ждать месяцы вслепую. Исторический causal proxy
показал:

- current shared exit: `-1.61%` bear и `-3.58%` recent;
- без SPY gate: `-8.70%` и `-7.28%`, значит защита полезна;
- тот же selector с 22-session hold: `-0.38%` и `+54.29%`;
- широкий exit: `-2.67%` и `+15.25%`.

Главный дефект локализован в слишком агрессивном shared exit, но `+54.29%`
не является прогнозом: universe survivor-only, arm не имеет допустимого
catastrophe stop. Две дополнительные SMA-комбинации не убрали bear loss и
остановлены, чтобы не оптимизировать один известный месяц.

Verdict: `REPAIR`, направление — monthly horizon + distant broker safety stop
+ Massive PIT + untouched exact-parity replay. SAFE_HOLD не менялся.

## Что не принято

1. **Универсальный `min_trades=159`.** Power зависит от заранее заданного
   минимально важного эффекта и дисперсии конкретной ноги. 159 корректно как
   диагностическая оценка для конкретного ATT1 sample, но не новый глобальный
   magic number.
2. **DSR >= 0.95 прямо сейчас.** Без честного effective independent trials
   такой gate даёт псевдоточность. Сначала provenance, затем оценка зависимости
   trial family, затем gate.
3. **Автоматический daily-reset defect.** `disabled=False` при новом UTC-day
   перевзводит именно дневной loss breaker. Удалять reset нельзя: это сделало
   бы дневную остановку бессрочной. Owner pause остаётся отдельным `TRADE_ON`.
4. **Массовый архив стратегий и документов.** Четыре стратегии действительно
   имеют устойчиво отрицательные семьи, но переносы пока не принимаются:
   registry/config/reference paths всё ещё ссылаются на active location.
   Корневой archive также оставляет битые document links. Ничего не удалено.
5. **«Графики Клода».** В tracked production-файлах нет изолированного diff,
   который можно безопасно принять. Есть backup монолита и untracked
   `web/static/live_chart_prototype.html`; без trade→decision→level provenance
   и visual regression это прототип, не production patch.

## Direct live truth

Проверено read-only `2026-07-28T11:47:54Z`:

- service `bybot`: active;
- Bybit equity / available: `$1020.10 / $1020.10`;
- positions: `[]`, position query OK;
- unrealized PnL: `$0`;
- 30d closed PnL: `+$0.29`, 10 trades;
- ATT1/live config не изменялись этой сессией.

## Ближайшие реальные ворота

| Контур | Что получено сейчас | Следующий доказательный шаг | Ориентир |
|---|---|---|---|
| XSEC | broad family PASS, 36/36 | PIT universe + funding/slippage + immutable shadow | 3–10 дней на V5 evidence, не обещание live |
| Alpaca | exit defect localized | distant-stop contract + Massive PIT + untouched replay | 3–10 дней на новый historical verdict |
| BOUNCE1 | exploratory only | virtual lifecycle + untouched window | 2–5 дней на shadow-ready receipt |
| Event retest | collector active | deadline coverage + frozen scorer | после 28 Jul 18:19 UTC |
| ATT1 | live tiny canary unchanged | N20 review, N30 scale discussion | sample-driven, не календарное обещание |

Самый вероятный путь к расширению торговли сейчас: XSEC risk-zero V5 первым,
затем repaired Alpaca historical candidate и BOUNCE1 virtual shadow. Ни один
из них не получает деньги автоматически.
