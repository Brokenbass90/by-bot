# Codex recovery session — 2026-08-11

За сессию закрыты четыре узких, но фундаментальных разрыва: доказана реальная
работа live profit protection, создана лаборатория отрицательных сделок,
исправлен невидимый для adapter universe contract и укреплен zero-risk XSEC
shadow. Ни одна исследовательская находка не получила деньги автоматически.

## 1. Live: что произошло с DOT и ADA

Direct broker/accounting reconciliation показала:

| Сделка | Фактический путь | Net broker PnL | Классификация |
|---|---|---:|---|
| DOTUSDT short 66 | TP1 `36.3`, TP2 `29.7` | `+0.1072467 USDT` | TP ladder |
| ADAUSDT short 116 | TP1 `63`, BE/ATR trail, stop `53` | `+0.4193142 USDT` | trailing protected |

ADA действительно защитила импульс: runner после TP1 поднял stop, затем
ATR-trail обновил биржевой stop примерно до `0.18745`; остаток исполнился около
`0.1875`. Это не имитация trailing. DOT закрылась TP1+TP2, не trailing.

Ограничение: обе позиции открыты до atomic stale-fill release, поэтому их плюс
не доказывает post-fix ATT1 и не входит в clean N20. После закрытия direct broker
flat, service active, heartbeat fresh. На момент снимка money authority только
ATT1 short-only с `risk_mult=0.10`; новые sleeves не активировались.

Resilience gap остается: runner пишет защитный SL на биржу, поэтому последний SL
сохранится при смерти процесса. Но exchange-native TP ladder по умолчанию
выключена; при долгом outage TP1/TP2 и дальнейшие trail updates не гарантированы.
Это отдельный shadow/failure-injection проект, не повод включать exchange TP
без проверки partial-fill/reconciliation semantics.

## 2. WS transport guard

`ACTIVE: CRITICAL ... new_entries_blocked=1` означает, что несколько контрольных
окон зафиксировали reconnect/disconnect/handshake timeout и guard закрыл только
новые входы. Existing биржевые stop не исчезают, а после восстановления runner
продолжает management. `RECOVERED: OK` означает нормализацию последующих окон.

Сейчас guard inactive, critical streak zero. Утверждение AI, что причина точно
во внешней сети, не подтверждено: те же симптомы возможны при VPS CPU/IO stall,
event-loop blockage или upstream failure. Нужна корреляция `mtr`, CPU/IO/event
loop lag и shard logs по timestamp.

## 3. Лаборатория отрицательных сделок

Добавлен `research_lab/negative_trade_lab.py` и contract tests. На входе —
immutable `trades.csv`; на выходе:

- source path/hash и data-quality receipt;
- `net/gross/cost` в R, t-stat, PF, WR;
- buckets по strategy/symbol/side/time/exit path/regime/HTF/hold/risk/cost;
- Markdown/JSON/CSV evidence;
- `ai_proposal_packet.json` без raw orders, secrets, broker и promotion authority.

Это отвечает на вопрос «почему минусит» на диагностическом уровне. Bucket не
считается причинностью: из него разрешено сформировать только одну
предзарегистрированную гипотезу, после чего нужны time/symbol replication.

### Squeeze long — первый восстановленный case

`620` сделок, `24` символа, gross `-40.3728R`, costs `90.9689R`, net
`-131.3417R`, mean `-0.2118R`, `t=-6.7415`, PF `0.5368`.

Диагноз: `negative_gross_edge_plus_cost_drag`. Даже нулевая комиссия не спасает
текущую логику входа. Exit paths:

| Exit path | Trades | Gross R | Costs R | Net R |
|---|---:|---:|---:|---:|
| plain `TRAIL_SL` | 309 | -161.687 | 44.791 | -206.478 |
| `SL` | 62 | -63.998 | 12.024 | -76.022 |
| `TP1+TRAIL_SL` | 106 | +40.137 | 15.226 | +24.911 |
| `TP1+TP2+TRAIL_SL` | 139 | +145.421 | 18.275 | +127.147 |

Полное 5m MFE/MAE покрытие `620/620` показывает:

| Фенотип | Trades | Avg MFE | Avg MAE | Смысл следующего теста |
|---|---:|---:|---:|---|
| stop then reversed | 276 | `1.102R` | `-0.638R` | state/geometry, не слепо wider stop |
| stopped no reversal yet | 175 | `0.302R` | `-0.699R` | entry confirmation/filter |
| gave back profit | 133 | `1.339R` | `-0.412R` | exit/ratchet ablation |
| entry failed fast | 36 | `0.048R` | `-1.622R` | reject toxic entry state |

Forensics PnL `-496.02` дан в долларах harness, а `-131.34R` — risk-normalized;
эти единицы нельзя складывать или сравнивать как одно поле.

## 4. ATT1 и скрытые allowlists

Wide ATT1 CSV дал `823` сделки на `64` реально торговавшихся символах: gross
`+19.3395R`, costs `48.1093R`, net `-28.7698R`, mean `-0.0350R`, `t=-0.987`,
PF `0.932`. Это cost-killed weak gross edge, а не переносимость major edge на
широкий рынок. Major-only ATT1 остается отдельной гипотезой; wide rollout
отклонен.

`inplay_retest_v3` уже имел legacy `IRV3_ALLOW/DENY`, поэтому утверждение
«ручки не было совсем» было неточным. Реальный дефект: стандартный adapter их
не обнаруживал. Добавлены `IRV3_SYMBOL_ALLOWLIST/DENYLIST` и config aliases с
presence-based precedence; legacy contract и defaults сохранены. Preflight
теперь падает, если две заявленные CSV universes дают одинаковое множество.

## 5. XSEC V3 zero-risk shadow

Существующий screen `xsec_v3_shadow_20260726` жив, order authority false. В
cycle добавлены:

- exchange `launchTime` maturity audit `>=390 days`;
- audit frozen universe на каждом цикле и fail-close при `<14` mature symbols;
- immutable entry prices и per-symbol markout contributions;
- anomaly flag при `|symbol return|>75%` или `|phase return|>25%`;
- запрет anomaly phase returns попадать в leverage history.

Текущий universe случайно проходит `62/62`, но старые экстремальные markout
(`+61%` и т.п.) не имеют сохраненной entry attribution и не являются forward
доказательством. Новые ledger events уже будут аудитопригодными.

## 6. Claude: направление и необходимые поправки

Правильно: расширять universe, доказывать ручки preflight, считать R и
cost/stop-width economics, искать independent leg, строить BTC state table, а
не бинарный SMA switch.

Поправки:

- wide ATT1 отрицательна; нельзя переносить major result на 62/64 symbols;
- maker разумен для возвратного ATT1, но ухудшает impulse breakout из-за
  adverse selection;
- XSEC уже запущена в V3 shadow; задача была укрепить integrity, а не запускать
  второй дубликат;
- monolith использует Elder V2 path, но policy держит его disabled/risk zero;
  V3 research-only и overconstrained. «Рабочая V2 против сломанной live V3» не
  подтверждается direct code/policy evidence.

## 7. Что не успело и почему

- Не скачана широкая Bybit funding history: существующая cross-exchange база
  покрывает лишь 8 символов и 180 дней.
- Не собрана PIT-aware Alpaca daily база на 100–200 акций: имеющиеся yfinance
  данные несут survivor/corporate-action ограничения.
- Не выполнен новый retest3 wide run: пять постоянных screen уже заняли пять
  вычислительных lanes; шестой тяжелый job повысил бы риск взаимного убийства.
- Не включены 85 индексированных модулей: inventory не равен полезности.
- Не давался капитал XSEC/Elder/новой ноге и не менялся live risk.

Это не ожидание. За вычислительным временем продолжают работать пять
research/shadow процессов; следующий тяжелый lane стартует после освобождения
слота, с preregistration и exact receipts.

## 8. Проверка

- Focused tests: `40 passed in 0.30s`.
- `py_compile`: pass для измененных Python modules.
- `git diff --check`: pass для scoped diff.
- Reserved `2025-10..2026-06` holdout не читался.

## 9. Следующий falsifiable пакет

1. Squeeze: три независимых ablations по фенотипам; без reserved holdout.
2. Retest3: one-slot/wide reachability smoke с universe proof.
3. XSEC: накапливать только новые attributable forward markouts.
4. Funding: broaden public history, listing/delisting metadata и cost model.
5. Equities: PIT-aware daily bundle и exact Alpaca live-contract replay.
6. Elder: V2/V3 одинаковый adapter/data/universe/cost/exit manifest.
7. AI graph analysis: proposal-only chart cards, затем machine reproduction.
