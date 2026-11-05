# Polymarket: точные условия отказов resolution/V3,5Nov2026

Диагностика по сохранённым данным; producer/judge/исторические измерения не
запускались, существующие сигналы/цепочки/интенты/финансовые права не менялись.

## Resolution: дефект decoder Codex, не34новых неудачных сигнала

В codex_hook.log подтверждены34 issue `'resolved_at'`; в сохранённых polls это
34ответа по5рынкам:25+1+1+5+2. Consumer проходит status=resolved, затем обращается
к row['resolved_at'] и получает KeyError. Все5вариантов new_version_q=true имеют
price/proposed_price/reproposed_price/last_update_timestamp/question_id, но НЕ
имеют resolved_at и payouts. Другой поддержанный вариантAPI имеет ISOresolved_at
и payout vector — поэтому ранее были успешные полные joins.

Это неполная поддержка вариантов ответа в моём parser. Точный failing access:
research_lab/polymarket_signal_cycle_v1.py:277, до проверки payouts на281.
Просто заменить [] на.get недостаточно: отсутствуют ещё payout/time semantics.
last_update_timestamp нельзя молча переименовать в независимое времяresolution,
а price — в исполнение или деньги. Для этих записей outcome покаUNKNOWN; 0PnL
не записан. Старые measurement manifests/intake не переигрывать. Нужен отдельный
минимальный decoder актуального documented response, не второй E2pipeline.
В этом диагностическом шаге consumer/runtime не изменены.

[34 raw-poll привязки/варианты](evidence/poly_e2_failures_20261105/resolution-schema-captures.json).
Официальная [resolution API](https://docs.polymarket.com/api-reference/markets/get-resolution-state)
описывает condition-grain ответы из разных lifecycle источников.

## V3: SOURCE_PROVENANCE означает неверно названный исходный журнал котировки

Условие qualify_v3: ровно1строка с market_id+source_sha256 в data/<source>/knigi.jsonl,
и int(row.t*1000)==signal.received_ms. Для всех6SOURCE_PROVENANCE совпадений в
указанном source нет; единственная точная raw-строка с этим SHA и правильным t
найдена в ДРУГОМ из двух разрешённых журналов. Это не повреждение sports witness:
до проверки sports frame выполнение ещё не дошло.

Producercb6c6bd… сейчас маркирует source через m['src'] (источник registry, строка128),
но raw для hash берёт из объединённого kn_raw[(market_id,t,side)] без source
(строки62/119). Источник registry и источник фактической котировки расходятся.
Claude: сохранять lineage фактически выбранной raw-строки вместе с её source,
не маркировать её по registry. Consumer не будет искать «подходящий» источник
вместо заявленного. Старые строки/prevSHA не исправлять и повторно не оценивать.
Новый producerSHA потребует явной проверки совместимости, без слепого repin.

## V3: STALE_SCORE — отдельная проверка возраста на Mac

Условие: consumer_observed_ms−score.score_on_mac_ms<=120000. Точное время вызова
проверки отдельно не сохранено; blocked_ms записан после отказа. Но оба счёта уже
старые на signal_ms: Lakers–Kings171890ms, Pacers–Grizzlies261426ms. Значит отказ
не вызван задержкой consumer после записи (1537/1411ms до blocked receipt).
Возраст на blocked receipt173427/262837ms. Лимит120s не расширять/не ретаймить;
producer может отбрасывать уже устаревший score до emit, сохраняя отдельную QA.

На момент проверки8V3отказов (первоначальное сообщение перечисляло3):

| signal_observation_id | Матч | Условие | Declared → actual quote source / возраст |
|---|---|---|---|
| 1136ba6f4eb17d2559ef174b | Hawks vs. Wizards | SOURCE_PROVENANCE | poly_sport_shiroko → poly_monitor |
| 162f354a2e5b274913d6ae0d | Lakers vs. Kings | STALE_SCORE | 171890ms at signal |
| 40c8850fc3d53b64956125a9 | 76ers vs. Pistons | SOURCE_PROVENANCE | poly_monitor → poly_sport_shiroko |
| 6200f17478b884d7e3ca80ba | Pacers vs. Grizzlies | STALE_SCORE | 261426ms at signal |
| 673cf68fddf2f69f5ac48055 | Jazz vs. Pelicans | SOURCE_PROVENANCE | poly_sport_shiroko → poly_monitor |
| 6a7d5cd2664419b9dda2d1ad | Heat vs. Clippers | SOURCE_PROVENANCE | poly_sport_shiroko → poly_monitor |
| bb21cf3117133e7e48cf3450 | Mavericks vs. Spurs | SOURCE_PROVENANCE | poly_sport_shiroko → poly_monitor |
| fd46e85d7aec8cc62c84a433 | Timberwolves vs. Rockets | SOURCE_PROVENANCE | poly_sport_shiroko → poly_monitor |

[Все точные SHA/offsets/timestamps](evidence/poly_e2_failures_20261105/v3-exact-conditions.json),
[repro read-only](evidence/poly_e2_failures_20261105/probe-v3-source-readonly.py).
Проверены только исходные котировки/отказы: следующие gates не объявлены PASS.
