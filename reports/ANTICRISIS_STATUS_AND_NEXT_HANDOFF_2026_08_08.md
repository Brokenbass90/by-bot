# Антикризисный статус и следующий хендофф — 2026-08-08

## Главный операционный итог

ATT1 снова может входить. Причиной отсутствия сделок был календарный expiry
2026-08-05, а не новые API-ключи. Владелец многократно разрешил продолжение
стратегии; expiry удалён, tiny-risk оставлен **0.10**, short-only и восемь
символов не изменены. После flat-restart Bybit auth подтверждён, сервис active,
позиций нет. Новый чистый операционный cohort начинается с
`2026-08-08T05:04:01Z`.

Ноль позиций в `bull_trend` не является сам по себе неисправностью: ATT1 —
short-only и может долго не находить валидный сигнал. Неисправностью будут
свежие `BLOCKED ... canary expired`, auth errors, stale heartbeat или
несогласованная биржевая позиция.

## Состояние контуров

| Контур | Текущий факт | Решение |
|---|---|---|
| ATT1 crypto | live tiny 0.10, short-only, auth OK, flat | продолжать новый broker-reconciled cohort; не повышать риск по старому mixed cohort |
| BOUNCE1 BTC/ETH | exact replay: 3/3 положительных окна, 41 сделка; targeted shadow deployed 2026-08-08 | prospective risk-zero lifecycle активен; малая выборка, денег нет |
| XSEC v3 | 11 закрытых markout, 4 положительных, сумма −6.54% | не продвигать; продолжать диагностику фаз и executable costs |
| Funding positioning | 42 закрытия, 66.7% положительных, median +746.8 bps | продолжать; FAIL concentration из-за BLESS 69% |
| Funding arbitrage | прежняя экономика после полного исполнения недостаточна | оставить дешёвый paper lifecycle, не основной исследовательский бюджет |
| SQB1 squeeze breakout | offset-1 replay 747–3567 сделок, все сетки глубоко отрицательны после затрат | terminal FAIL текущей формулировки; holdout не трогать |
| FX/CFD legacy | D1 carry, H4 momentum/retest/mean-reversion отрицательны OOS/stress | старые price-only семьи закрыты; строить новые cross-pair/session/cross-market гипотезы |
| Alpaca live | SAFE_HOLD, ABBV/SCHW, broker stop coverage 2/2 | не добавлять $3000; сначала доказать fractional trail, fill reconciliation и rotation parity |
| Alpaca adaptive | fresh risk-zero decisions, 79 symbols, orders disabled | продолжать PIT/shadow; это исследование, не текущая live-ротация |

## Что принято из работы Claude

Принято и уже сохранено в Git: data-coverage guard, causal replay,
Purged CV, significance/selection diagnostics, SQB1 performance repair и
исследовательские тесты. Эти инструменты нашли ложное 540-дневное покрытие,
неустойчивость геометрических классов и провал SQB1 после исправления
same-bar bias.

Не принято в live: post-hoc `ATT1_MIN_ENTRY_DIST_ATR`, тезис «ATT1 на самом
деле continuation», некалиброванные `edge_monitor/dd_throttle/oos_selector`,
автоматическое управление слотами priority-router и любые результаты без
exact source/config/data parity. DSR по проверенным ATT1-классам ниже 0.95.

## AI-оператор и forensics

Сообщение от 2026-08-07 в основном корректно:

- `missing_candles` означает пробел в post-hoc forensic cache, а не доказанный
  сбой live-свечей или выхода;
- rolling 120d — смешанный исторический cohort, не вердикт текущего ATT1;
- N<20 недостаточен для promotion.

Поправки: IVB1 N13/PF1.258 слишком мал и стар для продвижения. Mixed live
PF0.709 не может закрыть текущий ATT1, но 23 исторические ATT1 сделки с
PF0.856 и множеством `gave_back_profit` — реальная задача для exit-quality
research. `LIVE_TRUTH_STALE_OR_CONFLICTING` был верным fail-closed ответом для
старого snapshot; direct truth теперь обновлён.

## Исправления этой сессии

1. ATT1 переведён с календарного expiry на постоянное owner approval при
   неизменном risk 0.10.
2. Исправлен fractional stop ratchet Alpaca: replace-order больше не отправляет
   дробный `qty`. Broker acceptance проверяется в ближайшее открытие рынка.
3. Telegram daily digest оставлен один раз в 08:00 UTC. Повторный Alpaca-only
   digest и его watchdog удалены. Отдельный proof-of-life каждые три часа
   оставлен как инфраструктурная телеметрия.
4. Локальный deterministic AI-аудитор запущен; он нашёл stale AI context и
   много потенциально недостижимых модулей. Ollama установлена, но ещё не
   подключена к Telegram/web-чату и не имеет права менять риск или ордера.

## Ближайшая очередь

1. Накопить N20 в уже запущенном BOUNCE1 BTC/ETH prospective risk-zero
   lifecycle; проверить exact source SHA и geometry decision/fill/exit parity.
2. Заморозить новый funding-positioning cohort и повторить robustness после
   20–30 новых закрытий.
3. На открытии рынка подтвердить Alpaca fractional stop replace, затем
   восстановить broker-fill ledger и провести одну полную безопасную rotation.
4. Реализовать новые FX/CFD causal families: cross-pair residual strength,
   London/NY session transfer, rate surprise, commodity-FX, XAU отдельно,
   index session continuation и volatility expansion.
5. Ввести независимый parity layer: VectorBT/Optuna уже доступны в
   `.venv-research`; следующими идут property tests, indicator parity и один
   независимый event-driven replay. Не подключать библиотеку к live пути до
   совпадения результатов.
6. Подключить Ollama как критика исследований и классификатор логов. В чат —
   только через явный model-router с маркировкой источника и proposal-only.

## Масштабирование Alpaca

$3000 сейчас преждевременно. Лестница: подтвердить trail replace на рынке →
исправить DATA_INVALID ledger из broker fills → получить 20–30 уникальных
shadow-решений → завершить одну rotation с точным паритетом → масштабировать
$500 → $1000 → $1500 → $3000. Текущая live Alpaca — защищённый накопительный
эксперимент, а не доказанный автономный доходный контур.

## Оценка оставшейся работы

Для связной следующей версии, а не «идеального навсегда» продукта: примерно
7–10 сфокусированных сессий. Из них 2–3 на следующий crypto shadow и
геометрию/parity, 2 на Alpaca reconciliation/rotation, 2–3 на новые FX/CFD
семьи, 1–2 на open-source parity и Ollama router. Новый чат можно начинать
сразу с этого файла; ждать завершения всей очереди не требуется.
