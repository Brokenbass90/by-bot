# Open-source crypto family prefilter — 2026-08-02

## Решение

VectorBT 1.1.0 и Optuna 4.9.0 теперь не просто перечислены в requirements: они установлены в отдельное `.venv-research`, smoke-test пройден, а полный research-only прогон 170 вариантов пяти семейств выполнен.

Ни один вариант пока не получает promotion. Прогон выявил две ошибки исследовательского дизайна и одну полезную закономерность: книга резко меняет знак между режимами, поэтому long/short должны отбираться отдельно и допускаться текущим режимом, а не смешиваться в одного вечного победителя.

## Что проверено

- 8 монет: BTC, ETH, SOL, LINK, ADA, LTC, DOT, SUI.
- H1-бары из локального 5m-cache.
- 170 вариантов: EMA trend, z-reversion, Donchian, sweep/reclaim, exhaustion reversal.
- Сигнал после закрытия бара, исполнение на следующем open.
- Base cost: 8 bps round trip; stress: 18 bps.
- Train selection не смотрит OOS; frozen finalists проверяются отдельно.
- Общая граница OOS: `2025-08-10 00:00 UTC` для всех символов.
- Отбор раздельно по `family × side`, чтобы более сильный long на train не удалял short-книгу и наоборот.

## Какие дефекты пойманы

1. **Разные календарные OOS.** Первый прогон делил каждую монету на 70% собственной истории. Из-за разных листингов BTC и SUI тестировались в разных режимах. Красивый exhaustion-long исчез после общей календарной границы. Этот промежуточный результат запрещён к использованию.
2. **Сторона терялась при отборе.** Выбор top-N только по family выбрасывал short-варианты, если long был лучше на train. Исправлено на `family × side`.
3. **Сильная режимная зависимость.** Лучшие short-варианты были глубоко отрицательны до общей границы и резко положительны после неё. Это не универсальный edge, а кандидат в режимно-условную книгу.

## Финальный общий split

| Кандидат | Train | OOS base | OOS stress | Вердикт |
|---|---|---|---|---|
| sweep/reclaim short, lookback 96h | mean -41.2%, 1/8 символов плюс | mean +41.6%, median +40.4%, 8/8 плюс, N=283 | mean +36.8%, median +35.7%, 8/8 плюс | Сильный regime flip. Только как условная bear-нога. |
| z-reversion short, 96h, z=1.5 | mean -41.0%, 2/8 плюс | mean +37.6%, median +25.2%, 8/8 плюс, N=375 | mean +31.4%, median +19.8%, 7/8 плюс | Сильный regime flip; требует причинного режима и native replay. |
| Donchian short, 96/24h | mean -20.1%, 1/8 плюс | mean +15.9%, median +17.4%, 6/8 плюс, N=297 | mean +11.8%, median +12.8%, 6/8 плюс | Более слабый и с двумя плохими символами; research-only. |
| Все финалисты long | различно | отрицательная median у каждого | отрицательная median у каждого | Не прошли этот общий OOS. |

Проценты — доходность отдельного VectorBT-портфеля на исследуемом сегменте, не годовой прогноз и не ожидаемая live-доходность.

## Следующий preregistered пакет

1. Сформировать простую causal regime state machine только из прошлых данных: bull / bear / transition с гистерезисом и minimum dwell.
2. На train фиксировать соответствие: long-family разрешена только в bull, short-family — только в bear; transition остаётся cash или отдельной mean-reversion ногой.
3. Проверить frozen rule на нескольких общих календарных walk-forward folds, а не на одной границе.
4. Победителей перенести в native event-driven replay с реальным stop/exit, общей моделью сайзинга, динамическим PIT-universe и symbol-LOSO.
5. Только после этого — shadow-карточки и сравнение `signal geometry hash` между scanner, strategy и journal.

## Ограничения

- VectorBT — фильтр большого пространства, не источник live-решений.
- Здесь ещё нет стакана, partial fills, funding и portfolio slot competition.
- Универсум фиксирован восемью монетами и пока не PIT-dynamic.
- OOS уже просмотрен; любые последующие изменения правил требуют новых untouched folds.
- Live и Heroku этим исследованием не менялись.

## Артефакт

`reports/research/vectorbt_crypto_family_prefilter_common_split_side_20260802/result.json`
