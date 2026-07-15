# Alpaca exact-parity materialization — 2026-07-15

Статус: `BLOCKED_FAIL_CLOSED`; SAFE_HOLD не изменён; performance не вычислялся; broker/live/env не затрагивались.

## Итог

Старый exact-parity preflight был концептуально правильным, но почти полностью пустым: девять обязательных артефактов не были закреплены. Более того, его source receipt теперь честно показывает drift двух reference-файлов после последующих исправлений, а forward-window, начинавшийся 2026-07-13, уже нельзя задним числом объявить untouched.

В этой сессии материализована максимальная безопасная часть основы:

- hash-pinned XNYS session-ledger reader и точный builder `last completed calendar-month close -> next XNYS session open`;
- отдельный `daily close -> next open` schedule для отрицательного daily-rotation control;
- adverse cost на каждом входе/выходе, opening-gap stop, отсутствие favorable target-gap credit и `stop_first` на неоднозначном OHLC-баре;
- один research-only shared exit: initial stop `2 ATR`, target `3.2 ATR`, BE `0.8R`, trail `1.5 ATR`, максимум `22` сессии; stop из текущего completed bar начинает действовать только со следующей сессии, чтобы не угадывать порядок high/low внутри daily bar;
- daily close MTM, intramonth portfolio-stop primitive и daily max drawdown с initial capital как первой вершиной;
- write-once materialization receipt: повторная запись в тот же путь запрещена;
- synthetic conformance PASS; broker-lifecycle exact conformance намеренно остаётся false.

Это ещё не backtest runner и не доказательство доходности. Это исполнимая и проверяемая рама, которая не даст будущему runner снова сделать same-close, monthly-DD вместо daily-DD или разные exits для сравниваемых arms.

## Что найдено в локальных данных

Локальный SPY cache дал `730` наблюдаемых торговых дат с 2023-08-11 по 2026-07-10 и `35` диагностических month-close/next-observed-open pairs. В каталоге parity cache проинвентаризировано `59` файлов. Все файлы hash-pinned в receipt.

Эти данные имеют статус только `DIAGNOSTIC_ONLY_NOT_XNYS_AUTHORITY` / `NOT_PIT_OR_CORPORATE_ACTION_PROOF`, потому что:

- наличие SPY-бара не доказывает полный официальный XNYS holiday/early-close calendar;
- fixed modern ticker set не является историческим point-in-time universe;
- adjusted OHLC не заменяет ledger splits/dividends/mergers/delistings, известных на момент события;
- локальный cache не доказывает включение исчезнувших компаний и delisting return policy.

Поэтому реальные calendar rows в authoritative component receipt остаются пустыми. Диагностические rows не могут быть поданы в performance runner.

## Точные блокеры

| Blocker | Severity | Почему важен | Что требуется |
|---|---:|---|---|
| official XNYS session ledger | critical | иначе month-end и next-open могут быть ошибочными | CSV: `session_date,market_open_utc,market_close_utc,source_record_sha256`, одна строка на сессию, затем SHA256 pin |
| point-in-time universe | critical | fixed current universe создаёт survivorship bias | membership intervals с `effective_from/effective_to` и hash исходной записи |
| PIT adjusted daily market manifest | critical | нельзя доказать completed-bar-only и корпоративные корректировки | manifest файлов 1D OHLCV с SHA256, provenance/as-of и покрытием каждой PIT membership interval |
| corporate actions + delistings | critical | победители остаются, исчезнувшие компании теряются | event-time ledger splits/dividends/mergers/symbol changes/delistings и frozen delisting-return rule |
| Jul6–9 broker lifecycle | high | нельзя калибровать fills/gaps/costs и доказать live/replay exit parity | redacted orders/fills/events export, unique IDs, complete reconstruction, zero conflicts |
| broker-calibrated cost/slippage | high | nominal 5/10 bps пока только frozen assumption | calibration receipt, hash-linked к broker lifecycle |
| shared-exit broker conformance | high | synthetic tests не доказывают совпадение polling/live fills | replay каждого Jul6–9 lifecycle event через общий exit engine, zero unresolved mismatches |
| untouched forward | critical | окно с 2026-07-13 уже нельзя запечатать 15 июля | новый successor prereg с будущим start, sealed manifest до первого outcome bar |
| four-arm runner | high | без него нет общей daily-equity механики | строить только после acceptance всех inputs; никаких результатов раньше |

## Почему старый preflight нельзя «починить заменой hash»

Текущий повторный audit старого prereg вернул:

- `frozen_source_hashes_not_ready`;
- `contract_fingerprint_mismatch`;
- все required inputs blocked;
- shared executable exit не доказан broker lifecycle;
- Jul6–9 lifecycle не восстановлен;
- untouched forward не sealed.

Source drift возник в том числе после исправления drawdown/diagnostic semantics и развития live bridge. Перезаписать старые hashes означало бы переписать историческое evidence. Правильный путь — сохранить v1 как audit trail и создать successor freeze после получения PIT inputs и до нового будущего forward-window.

## Созданные артефакты

- `backtest/alpaca_exact_parity_contract.py` — pure research primitives; нет broker/network/env/order imports.
- `scripts/materialize_alpaca_exact_parity_inputs.py` — fail-closed materializer; performance не вычисляет; output write-once.
- `configs/preregistered/alpaca_exact_parity_materialization_v1_20260715.json` — source/diagnostic hashes и неизменяемый execution/MTM/exit contract.
- `reports/research/alpaca_exact_parity_materialization_v1_20260715/receipt.json` — immutable evidence receipt, `performance_computed=false`, `promotion_authorized=false`, `safe_hold_changed=false`.
- `tests/test_alpaca_exact_parity_materialization.py` — календарь, hash drift, next-open, costs/gaps, stop-first, causal trailing, max-hold, daily MTM/DD и write-once safety.

Focused verification: `18 passed` вместе с существующим exact-parity preflight и исправленным drawdown test.

## Следующий допустимый шаг

1. Получить PIT universe + corporate-action/delisting source и официальный XNYS ledger; pin hashes, не смотреть performance.
2. Восстановить redacted Jul6–9 Alpaca broker lifecycle и сделать cost/exit conformance.
3. Заморозить новый будущий forward-window до его первой торговой сессии; v1 forward не реанимировать.
4. Только после PASS всех inputs реализовать один four-arm runner с общей execution/cost/exit/daily-MTM механикой.
5. До verdict оставить monthly v38 в `SAFE_HOLD`: никаких buys, forced rotations, scale или перехода adaptive в live.

Вывод по качеству данных: текущая локальная выборка годится для диагностики формата и тестирования механики, но не годится для утверждения доходности или снятия SAFE_HOLD. Уверенность высокая: блокеры проверяются наличием, hashes и семантическими predicates, а не субъективной оценкой.
