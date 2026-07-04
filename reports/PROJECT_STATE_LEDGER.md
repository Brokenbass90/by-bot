# PROJECT STATE LEDGER — единая точка правды (обновляется каждую сессию)
Последнее обновление: 2026-07-01 morning (Codex). START HERE. План вперёд: reports/ROADMAP_V2_2026_06_30.md. Утренний статус: reports/MORNING_STATUS_2026_07_01.md.

## Принципы (не нарушать)
- АСИММЕТРИЧНЫЙ R:R: тейк 2-3R, стоп ~1R (прибыль через R, не винрейт).
- Свипы Корпатого ДА, но отбор по OOS-плато, не по in-sample (иначе overfit).
- Фокус сместился на ФОРЕКС-костяк + механику; directional переписываем OOS-first, не хороним.
- OOS-first: in-sample PASS ≠ успех. Судим по OOS.
- Не удаляем/не «замораживаем» идеи — спорное в архив, не в корзину.
- Деньги — в механические эджи (carry) + Alpaca; directional крипта должна
  ЗАСЛУЖИТЬ место через честный OOS.
- ИИ = аналитик/настройщик/менеджер В РЕЛЬСАХ, НЕ генератор кода (это нас подвело).
- Claude не трогает сервер/деньги — готовит код+артефакты; Codex деплоит/гоняет;
  деньги заводит владелец.

## НОВЫЙ ФУНДАМЕНТ (построен Claude, под тестами — 63 зелёных)
| Модуль | Что | Тесты |
|---|---|---|
| `bot/market_context.py` | детектор уровней: горизонт. кластеры, наклонные(R²,valid,min_slope), HVN, VWAP, classify_channel, nearest_broken_level, atr(exclude_last), build_context(max_age,exclude_last_atr) | 19 |
| `bot/volume_exit.py` | ранний выход по затуханию объёма + impulse-gate | 11 |
| `bot/strategy_breaker.py` | авто-роллбэк рукава (net-pnl/серия/expiry) | 11 |
| `bot/carry_neutral.py` | delta-neutral carry мозг (basis/liq/rebalance guards) | 9 |
| `bot/adaptive_context.py` | ИИ-настройщик параметров (rule-based + tuner-hook DeepSeek) | 5 |
| `scripts/market_survey.py` | обзор рынка: где какой эдж сейчас | — |
| `scripts/render_levels.py` | визуализация уровней | — |
| `scripts/market_survey.py` | обзор рынка: режим+структура по всем символам -> где какой эдж | — |

## СТРАТЕГИИ-НОГИ
| Файл | Статус | Заметка |
|---|---|---|
| `alt_trendline_touch_v1` (ATT1) | LIVE canary 0.10 short-only | редкий, пока 0 входов (нет наклонки) |
| `alt_resistance_fade_v2` (ARF2/пила) | research | OOS no-go; vol-filter ВКЛючён (fix); нужен упрощ.+WF (Codex) |
| `alt_support_bounce_v2` (ASB2) | research (тест) | ждёт 240d WF |
| `alt_channel_bounce_v1` (ACB1) | research (тест) | двусторонний канал; ждёт 240d WF |
| `inplay_retest_v3` | заменён на V4 | baseline PF 0.868 |
| `inplay_retest_v4` (НОВ) | research (5 тестов) | быстрый вход у уровня + асимметр. R:R (tp2.5/sl1) + свежесть + setup B (ретест пробоя); ждёт WF |
| `spike_fade_v3` | кандидат-диверсификатор | PF 1.99, редкий |
| `elder_*` | фильтр, не движок | проходил WF-22 до temporal-фикса |
| 71 прочих | архив/заморозка (по инвентарю) | не удалять |

## ДЕНЕЖНЫЕ КОНТУРЫ
- Alpaca v38: PF 6.47, ждёт live-аккаунт+$500+ключи (владелец) → dry-run → live.
- Cross-exchange carry: кандидаты GWEI/SLX; мозг готов; нужна обвязка ордерами (Codex).
- ATT1 short: live, риск 0.10, ждёт сетап.
- Pair stat-arb (`pair_stat_arb_v1`): cointegration, beta/z-score/half-life + СВОЙ WF тулинг (walkforward_pair_arb/validate_pair_arb) — закодирован, НЕ валидирован. Механический #2.
- Basis arb (`basis_arb_v1`, 382 стр) — закодирован, не валидирован.

## PENDING — CODEX (батч к коммиту/прогону)
- Закоммитить весь новый набор (фундамент-апгрейды, adaptive_context, render, ARF2 fix).
- ARF2: упростить параметры (убрать HVN/VWAP/recency веса) + ATR на rows[:-1] + честный WF.
- InPlay V4 (вход 1m/лимит у уровня, свежесть уровней).
- Carry: re-gate на высоком funding + delta-neutral обвязка.
- FX/XAU strict research (бесплатные данные) + Alpaca dry-run.

## PENDING — CLAUDE (локально)
- ASB2 + ACB1 adaptive ✓. СТОП пилить фичи на непроверенных ногах.
- Следующее: НЕ код, а WF-валидация (Codex). broken-level — опционально позже.
- Докрутить ASB2/ACB1 под broken-level + свежесть.
- По готовности: AdaptiveContextProvider → DeepSeek-tuner (когда будет API-бюджет).
- РЕФАЙН: sloped require_unbroken мерить на недавнем сегменте, не на всём окне (survey показал valid_sloped=0 — слишком строго).
- Survey-вывод: наклонные редки -> приоритет range/horizontal ноги, не ATT1.

## PENDING — ВЛАДЕЛЕЦ
- Завести Alpaca live $500 (реальный контур).
- Отдавать Codex батчи; носить ответы DeepSeek/GPT по аудиту.

## КЛЮЧЕВЫЕ ДОКИ (reports/)
- `COURSE_CORRECTION_2026_06_30.md` — разворот после OOS.
- `AUDIT_VERDICT_AND_FIXES_2026_06_30.md` — проверка claims DeepSeek + фиксы.
- `AUDIT_BUNDLE_2026_06_30.md` — карта кода для внешних ИИ.
- `WHAT_DIDNT_WORK_FOR_DEEPSEEK_2026_06_30.md` — для консультаций.
- `STRATEGY_INVENTORY_2026_06_29.csv` — все 91 с бакетами.
- `FUNDING_CARRY_READINESS_2026_06_29.md`, `PORTFOLIO_AND_AI_MANAGEMENT_PLAN_2026_06_29.md`.

## ОБНОВЛЕНИЕ 2026-06-30 (день, Claude — новый чат)
- Ночной WF-батч Codex НЕ вернулся (нет артефактов 30-06). Очередь обновлена: reports/CODEX_QUEUE_2026_06_30_PM.md.
- CARRY (механич. #1) на honest-учёте В МИНУСЕ: arb_roi_estimate.json 125 циклов WR35% mean -0.02% proj -5.7%/мес. НЕ live до ре-гейта по net-за-цикл + delta-neutral.
- PAIR-ARB: ядро коинтеграции чистое (аудит), но эджа нет на локальных данных (3/4 пар минус, 1 PF-выброс на 5 сделках). Данных мало -> нужен WF на сервере. См. reports/PAIR_ARB_LOCAL_SANITY_2026_06_30.md, reports/WF_AND_LIVE_HONEST_READ_2026_06_30_PM.md.
- Подтверждено: единственный доказанный плюс = Alpaca v38, ждёт $500 live (владелец).

## ДОБАВЛЕНО 2026-06-30 (range-детекторы, Claude)
- Range-детекторов ТРИ и они не общие; classify_channel(flat~33%) vs choppiness(range~8%) расходятся в 3-4x. Лучший (forex/regime 3 меры) юзает лишь 1 стратегия. Живая пила ARF1 сегодня 0/45 (гейт блокирует), ARF2 OOS no-go. План: унифицировать детектор (CI&vol&adx), асимметр R:R, фокус пилы -> форекс (ranges чище). См. reports/RANGE_DETECTOR_AUDIT_2026_06_30.md

## ДОБАВЛЕНО 2026-06-30 (range_filter + роадмап v3, Claude)
- bot/range_filter.py ГОТОВ под тестами (tests/test_range_filter.py, 7 зелёных; фундамент 78). Единый range-гейт: комбо 3 мер + classify_channel + горизонт/наклон уровни + сплит long_ok/short_ok. Codex: подключить ко всем bounce/fade ногам -> reports/RANGE_FILTER_WIRING_2026_06_30.md
- Зафиксировано видение слоёв: reports/ROADMAP_V3_TECH_STACK_2026_06_30.md (пила->пампы->инплэй->элдер->пробои; инварианты: short/long сплит, ИИ-аналитик, крипта+форекс, уровни наклон+горизонт, OOS+асимметр R:R).

## ДОБАВЛЕНО 2026-06-30 (pump_exhaustion, Claude)
- bot/pump_exhaustion.py ГОТОВ под тестами (tests/test_pump_exhaustion.py 6 зелёных; фундамент 84). Слой 2 роадмапа: детектор истощения пампа/дампа. Вход на фейд ТОЛЬКО после подтверждённого разворота (импульс+объём -> exhausted -> retrace>=33%). Сплит: пап->short_ok, дамп->long_ok. Анти-нож: растущий пап НЕ фейдится. Codex: подключить к pump_fade_* ногам вместо самодельного входа, затем WF.

## ДОБАВЛЕНО 2026-06-30 (retest_quality, Claude)
- bot/retest_quality.py ГОТОВ под тестами (tests/test_retest_quality.py 9 зелёных; фундамент 93). Слой 3 (инплэй): переиспользуемый скорер качества ретеста 0..1 (свежесть+близость+сила уровня+отбойный фитиль+объём) + best_retest (находит ближайший свежий уровень в банде). Сплит: support->long_ok, resistance->short_ok. Codex: подключить к inplay_retest_v4 / alt_support_bounce_v2 / alt_channel_bounce_v1 / пробоям / форекс-ретестам как общий грейдер входа.

## ДОБАВЛЕНО 2026-06-30 (elder_filter, Claude)
- bot/elder_filter.py ГОТОВ под тестами (tests/test_elder_filter.py 7 зелёных; фундамент 100). Слой 4: элдер как ФИЛЬТР-конфлюэнс (не самост. стратегия). tide (EMA fast/slow + MACD на HTF) + wave (Force Index/RSI) -> bias + гейты allow_long/allow_short, которые рукав AND-ит. require_with_tide=строгий режим. Float-safe (порог значимого EMA-зазора). Codex: обернуть bounce/fade/breakout ноги: short-only лога торгует только при allow_short, long-only при allow_long.

## ДОБАВЛЕНО 2026-06-30 (breakout_confirm + deploy handoff, Claude)
- bot/breakout_confirm.py ГОТОВ под тестами (tests/test_breakout_confirm.py 6 зелёных; фундамент 106). Слой 5: подтверждённый пробой (горизонт+наклон) с анти-ложным-выносом (буфер+объём/проследование+не reclaimed), сплит up->long_ok/down->short_ok, стыковка с retest_quality.
- ВСЕ 5 слоёв готовы: range_filter, pump_exhaustion, retest_quality, elder_filter, breakout_confirm (35 новых тестов). Тёрнкей-деплой под ночь: reports/DEPLOY_OVERNIGHT_2026_06_30.md

## ДОБАВЛЕНО 2026-07-01 morning (Codex)
- Live crypto живой: `dry_run=False`, `open_trades=0`, `hard_block=False`, `safe_mode=False`, режим `bear_chop`. Деньгами торгует только `ATT1 short-only risk=0.10`; горизонтальные рукава пока `risk=0.0`.
- На live-VPS остановлен stale `ars1_side_regime_repair_20260627`, который ел около `380MB` RAM и `88%` CPU. Available RAM выросла примерно `155MB -> 503MB`. Тяжёлые свипы нельзя гонять рядом с live на 1GB.
- Ночная локальная очередь завершилась:
  - InPlay V4 на `ADA/DOGE/SUI` около breakeven (`best +1.38R`, PF `1.039`, DD `7.55R`), на `LINK/SOL/ADA` отрицательный. Не live.
  - SpikeFadeV3 `LINK short-only`: `360d 29 trades +5.21R PF 2.107 DD 1.27R`; лучший crypto add-on candidate, но редкий и требует server gate.
- Старые большие backtest-цифры не считаем combat baseline: после closed-candle/next-open/cost/OOS/full-stack проверок часть эджа исчезла. Текущим тестам тоже не верим слепо; используем ladder: unit -> closed-candle -> next-open+costs -> OOS/WF -> stack comparison -> shadow parity -> tiny canary.
- Детали: reports/MORNING_STATUS_2026_07_01.md

## ДОБАВЛЕНО 2026-07-01 (Claude — разбор утра Codex)
- SpikeFadeV3 LINK short: честен по коду (closed-candle/next-open, без lookahead), но НЕ canary-ready. Флаги: 90/240/360d — вложенные окна (не независ. фолды), эдж во-фронт в недавних 240d; параметры bounded-свипнуты под LINK short (selection/overfit); N=29 мал. Гейт: reports/SPIKEFADE_V3_PRECANARY_GATE_2026_07_01.md (истинный WF train/test + fee-стресс + cross-symbol + monthly + shadow -> потом canary).
- Рамка на переработку принята: горизонталки не размораживаем, а wiring helper-слоёв (range_filter/retest_quality/breakout_confirm/pump_exhaustion/elder_filter) в ARF2/ASB2/ACB1/InPlay V4 -> OOS. InPlay V4 не боевой (PF ~1.04 лучший, минус на LINK/SOL/ADA) -> реворк через retest_quality+range_filter+elder.

## ДОБАВЛЕНО 2026-07-01 (Codex — реализация gate/wiring)
- Добавлен `scripts/spike_fade_robustness_gate.py`: rolling train/test WF, fee-stress и cross-symbol sanity для SpikeFadeV3 LINK short. Smoke прошёл, полный локальный gate запущен в `screen sfv3_robust_gate_20260701`; лог `logs/manual_research/sfv3_robust_gate_20260701.log`.
- `strategies/inplay_retest_v4.py` подключён к helper-слоям за флагами: `IRV4_USE_RETEST_QUALITY`, `IRV4_USE_RANGE_FILTER`, `IRV4_USE_ELDER_FILTER`, `IRV4_USE_BREAKOUT_CONFIRM`. Дефолтное поведение не меняется.
- Focused tests: `44 passed`. Детали: reports/INPLAY_V4_HELPER_WIRING_2026_07_01.md

## ДОБАВЛЕНО 2026-07-01 (уборка + тех-бэклог, Claude)
- УБОРКА: план reports/CLEANUP_PLAN_2026_07_01.md (архив, не корзина): кэши/tmp в .gitignore (дописано), 85 корневых .md -> docs/archive, ~71 FREEZE/ARCHIVE стратегий -> strategies/archive (после grep импортов+каталог), reports старьё -> reports/archive. Активная поверхность ~15-20 стратегий. Выполняет Codex (git mv; Claude из песочницы не может).
- ТЕХ-БЭКЛОГ качества: reports/TECH_QUALITY_BACKLOG_2026_07_01.md. P0: OOS-plateau selector (кодифицировать анти-оверфит отбор) + slippage в forex/engine. P1: vol-targeted sizing, maker-limit-at-level executor, корреляц.-гейт. P2: live edge-decay монитор, feature-слой. Рекомендация: следующим строить OOS-selector.

## ДОБАВЛЕНО 2026-07-01 (ROADMAP v4 + OOS-selector, Claude)
- ЕДИНЫЙ ПЛАН: reports/ROADMAP_V4_2026_07_01.md (START HERE forward): Фаза0 гигиена+анти-оверфит -> Ф1 wiring+WF -> Ф2 деньги(Alpaca/carry/pair-arb) -> Ф3 sizing/executor/corr -> Ф4 ИИ+масштаб.
- bot/oos_selector.py ГОТОВ под тестами (tests/test_oos_selector.py 9 зелёных; фундамент 115). P0-тех: кодифицирует анти-оверфит отбор — оценивает кандидатов по OOS-фолдам (frac_positive>=0.75, медиана>0, disp-штраф, peak-gate против один-окно-героя, min trades). select_robust/rank_all. Codex: прогонять ВСЕ свипы через него, не выбирать PF-пик руками. Проверено: SpikeFade на 2 окнах -> too_few_folds.

## ДОБАВЛЕНО 2026-07-01 (level_entry — лечим поздний вход, Claude)
- bot/level_entry.py ГОТОВ под тестами (tests/test_level_entry.py 8 зелёных; фундамент 123). Фаза3-тех: maker-лимит У уровня вместо входа по закрытию (корень провала InPlay). Тайт-стоп за уровнем -> высокий R (в тесте close-вход давал 1.47x шире стоп), асимметр. tp (rr2=2.5), chase-guard (не догоняем убежавшее), validity_bars, simulate_fill для честных бэктестов maker-филлов. Сплит support->long/resistance->short. Codex: подключить к level-ногам (IRV4/support_bounce/breakout) как планировщик входа; live-executor ставит лимит.

## ДОБАВЛЕНО 2026-07-01 (position_sizing, Claude)
- bot/position_sizing.py ГОТОВ под тестами (tests/test_position_sizing.py 9 зелёных; фундамент 132). Фаза3-тех: fixed-R sizing (1R одинаков на всех сделках независимо от ширины стопа) + портфельный risk-бюджет (max_open_risk_pct) + leverage-cap + опц. vol-target (режем риск при высоком ATR%). Codex: подключить как единый sizer во все ноги + WF.
- ВАЖНО (тест с учётом технологий): WF отражает хелперы ТОЛЬКО после wiring в ноги + движок должен звать реворкнутые ноги и maker-fill (level_entry.simulate_fill), иначе тест гоняет СТАРУЮ логику. Это записано как обязательное условие Фазы 1.

## ДОБАВЛЕНО 2026-07-01 (exposure_gate — P1 закрыт, Claude)
- bot/exposure_gate.py ГОТОВ под тестами (tests/test_exposure_gate.py 8 зелёных; фундамент 140). Портфельный корреляц.-гейт: кластер коррелированного однонаправленного риска (|corr|>=порог), scale-down/deny сверх бюджета; противоположная сторона ХЕДЖирует кластер; correlation_from_prices. Дружит со всеми ногами (единое правило риска для live+бэктест+ИИ). Codex: подключить в risk-manager перед добавлением сделки.
- Тех-бэклог P0/P1 ЗАКРЫТ: 9 модулей-технологий под тестами (range_filter, pump_exhaustion, retest_quality, elder_filter, breakout_confirm, oos_selector, level_entry, position_sizing, exposure_gate).

## ДОБАВЛЕНО 2026-07-01 (ресёрч инфополя, Claude)
- reports/RESEARCH_IDEAS_2026_07_01.md: №1 AI-legible decision bus (единая шина решений/фич — ИИ видит всё честно; флагман, строю следующим), №2 meta-labeling (López de Prado: вторичный take/skip+size над шиной, дружит со всеми ногами; усиливает реальный эдж, не создаёт), №3 вероятностный режим HMM-lite, №4 order-flow ТОЛЬКО как фича (эдж мал и затухает: VPIN +82->+38->+12bps), №5 triple-barrier разметка. Приоритет: bus -> meta+triple-barrier -> regime -> order-flow.

## ДОБАВЛЕНО 2026-07-01 (decision_bus + ресёрч2 + бриф DeepSeek, Claude)
- bot/decision_bus.py ГОТОВ под тестами (tests/test_decision_bus.py 8 зелёных; фундамент 148). Единая честная шина: build_decision из helper-состояний, attach_outcome, JSONL sink, summarize (win_rate/expectancy_R по strategy/side/regime) — surface для ИИ + meta-labeling + edge-decay.
- Ресёрч2: CPCV (purge+embargo, López de Prado) -> апгрейд WF против оверфита (ниже PBO); funding-экстремумы+ликвид-каскады -> кандидат МЕХАНИЧЕСКОГО крипто-эджа (H4). Бриф для DeepSeek: reports/FOR_DEEPSEEK_2026_07_01.md (5 гипотез H1-H5 + 7 вопросов, формат фальсифицируемых тестов).
- Codex-нота: WF-харнесс -> добавить purging+embargo (не вложенные окна).

## ДОБАВЛЕНО 2026-07-01 (cascade_reversal + разбор DeepSeek, Claude)
- bot/cascade_reversal.py ГОТОВ под тестами (tests/test_cascade_reversal.py 8 зелёных; фундамент 156). H4-детектор каскадного реверсала: полные триггеры DeepSeek (funding z>=2, OI-drop>=5%/15м, liq>=95п/4ч, тайминг 2-5 баров, сплит down->long/up->short). ЧЕСТНО: прошлый liquidation_cascade_entry_v1 упал (PF0.25) но на BTC/ETH+proxy+неполные триггеры -> H4 не опровергнут.
- DeepSeek подтвердил курс. Приоритет: Alpaca$500 -> H4(PF>1.3->canary) -> форекс(news-фильтр) -> meta(после 100+ сделок). Все фальсифицируемые тесты: reports/DEEPSEEK_RESPONSE_ACTIONS_2026_07_01.md. Слепые зоны: реальн.слиппедж альтов 5-10x, кризис-корреляция, психология, ребаланс-издержки.

## ДОБАВЛЕНО 2026-07-01 (wf_folds purge+embargo, Claude)
- bot/wf_folds.py ГОТОВ под тестами (tests/test_wf_folds.py 6 зелёных; фундамент 163). H5/CPCV-lite: purge_embargo_folds делит сделки на непересекающиеся OOS-фолды, PURGE сделок через границу (утечка) + EMBARGO пограничных; as_candidate() кормит oos_selector. Лёгкий (на 1GB ок). Codex: WF-харнесс -> генерить фолды через это, не вложенные окна.

## ДОБАВЛЕНО 2026-07-01 (news_session_filter, Claude)
- bot/news_session_filter.py ГОТОВ под тестами (tests/test_news_session_filter.py 9 зелёных; фундамент 172). H2: форекс news/session-гейт — блэкаут за block_before/after мин вокруг high-impact событий, блок тонкой азиатской сессии, флаг близости к круглым уровням (стоп-охота). Codex: подключить к форекс range/bounce ногам; в WF считать PF новостных vs чистых дней (гейт: новостной PF<0.8 -> фильтр обязателен).

## ДОБАВЛЕНО 2026-07-01 (Codex — commit/verification)
- Проверен и подготовлен к коммиту набор P0/P1-технологий Claude: `oos_selector`, `level_entry`, `position_sizing`, `exposure_gate`, `decision_bus`, `cascade_reversal`, `wf_folds`, `news_session_filter` + тесты. Focused suite вместе с существующими helper/InPlay/Spike тестами: `109 passed`.
- Исправлен `scripts/spike_fade_robustness_gate.py`: отсутствие кэша по cross-symbol теперь не валит весь gate, а пишется как skipped row. Первый полный gate упал на missing cache `NEARUSDT`; перезапущен `sfv3_robust_gate_20260701_v2` с кэшированными cross-symbols `SOL/SUI/DOGE/ADA`.
- Чистка проекта пока только подготовлена планом и `.gitignore`. Массовый перенос стратегий в archive делать только после grep импортов + проверки strategy catalog.
- Live-VPS safety: остановлен новый тяжёлый `arf1_structured_short_repair_20260627` рядом с live (`~446MB RAM`, `~82% CPU`). Available RAM восстановилась примерно `134MB -> 561MB`. Правило подтверждено: тяжёлые свипы только локально/research-host, не на 1GB live.

## ДОБАВЛЕНО 2026-07-01 (edge_monitor — анти-деградация, Claude)
- bot/edge_monitor.py ГОТОВ под тестами (tests/test_edge_monitor.py 7 зелёных; фундамент 179). Монитор деградации эджа: сравнивает LIVE realized R с backtest-baseline по рукаву -> статус healthy/watch/degraded/halt (decay-ratio, drawdown-R, losing-streak, negative-expectancy). assess_all читает decision_bus. Кормит strategy_breaker/ИИ. Codex: подключить как governor -> авто-throttle degraded, halt при breach. ЭТО ответ на «не деградировать годами».

## ДОБАВЛЕНО 2026-07-01 (champion_challenger — конвейер портфеля, Claude)
- bot/champion_challenger.py ГОТОВ под тестами (tests/test_champion_challenger.py 8 зелёных; фундамент 187). Жизненный цикл рукава: candidate--(oos_selector pass)-->shadow--(edge_monitor healthy)-->canary--(live healthy+exp>0)-->champion; degraded/halt-->demoted. run_registry + portfolio_view. Тянет ноги из ямы честно и авто-выбраковывает мёртвые. Codex: реестр состояний рукавов + периодический прогон.
- Технологий под тестами: 14. Полный конвейер отбора/промоушена/анти-деградации.

## ДОБАВЛЕНО 2026-07-01 (slippage_model + распараллеливание, Claude)
- bot/slippage_model.py ГОТОВ под тестами (tests/test_slippage_model.py 7 зелёных; фундамент 194). Калибратор слиппеджа (слепая зона DeepSeek #1): calibrate_from_fills (live expected vs actual -> median/p90 bps по символу), estimate_bps (калибровка/дефолт + context inplay×5/illiquid×8 + sublinear размер), apply_slippage. Codex: кормить таблицу в WF-движок -> честные издержки; писать live-fills для калибровки.
- INFRA: reports/RESEARCH_PARALLELIZATION_2026_07_01.md — Mac=research-хост, шардинг символов + caffeinate -> H4-данные/WF параллельно за часы. VPS только live+коллектор.

## ДОБАВЛЕНО 2026-07-01 (трейлинг+ликвидность+режим+чекпойнт, Claude)
- bot/trailing_stop.py (7 тестов): breakeven + Chandelier ATR-трейл, one-way, exit по стопу бара (без same-bar whipsaw); simulate_trail. Для ЭЛДЕРОВ и всех ног — даёт прибылям течь (в тесте runner дал +7.5R). Codex: подключить к элдеру/трендовым ногам.
- bot/liquidity_sweep.py (7 тестов): охотник за ликвидностью/плотности. Различает sweep_reversal (свип за уровень + возврат -> ФЕЙД/отскок) и break_hold (закрытие за уровнем -> ПРОБОЙ). Ответ на вопрос: плотности берут И отскок, И пробой — по close vs pool. Сплит сторон.
- bot/regime_hmm.py (8 тестов): HMM-lite вероятностный режим (bull/bear/range/high_vol) со sticky-переходами; regime_gate блокирует торговлю в high_vol (анти-деградация) + risk_scalar по уверенности.
- bot/run_checkpoint.py (5 тестов): возобновляемые прогоны — уснул/убился Mac -> рестарт с места (JSONL done-log+fsync). Обёртка: caffeinate + screen + этот чекпойнт.
- Технологий под тестами: 19. Фундамент 221.

## ДОБАВЛЕНО 2026-07-01 (интеграционный референс, Claude)
- reports/INTEGRATION_REFERENCE_2026_07_01.md: канонический порядок вызова 19 модулей в ОДНОЙ ноге (regime->сигнал->range->elder->news->level_entry->sizing->exposure->decision_bus->trailing) + бэктест-цепочка (simulate_fill+slippage->attach_outcome->wf_folds->oos_selector->edge_monitor->champion_challenger). Чтобы Codex вписал единообразно. Claude осознанно ПАУЗА в стройке — ждём реальные WF-цифры, не строим вслепую.

## ДОБАВЛЕНО 2026-07-01 (Codex — mechanics wiring)
- `backtest/portfolio_engine.py` теперь честно моделирует pending limit-сигналы: `entry_order_type=limit`, fill только при касании limit price, expiry через `limit_validity_bars`; обычные next-open сигналы не изменены.
- `strategies/inplay_retest_v4.py` получил `IRV4_USE_LEVEL_ENTRY`: Setup A/B строят maker-limit у уровня через `bot.level_entry`, не догоняют late-close, и сохраняют точные reject reasons.
- Focused suite: `56 passed`.
- Smoke: InPlay V4 `ADA/DOGE/SUI`, 120d, base close-entry `61 trades, -3.64R, PF 0.691, DD 6.75R`; с `level_entry` `11 trades, +0.31R, PF 1.25, DD 0.33R`.
- Smoke с `retest_quality + level_entry`, 240d: `ADA/DOGE/SUI` `22 trades, +2.61R, PF 2.52, DD 0.60R`; `LINK/SOL/ADA` `14 trades, -0.19R, PF 0.908`. Это НЕ live-grade, но первый позитивный end-to-end сигнал новой цепочки.
- SpikeFadeV3 robust gate: FAIL (`29 OOS trades, +0.93R, PF 1.144`, fee stress failed). Не canary.
- Добавлен `scripts/inplay_v4_mechanics_gate.py`: rolling train/test gate для реворкнутой цепочки `retest_quality + level_entry + pending limit fills + oos_selector`. Smoke gate прошёл технически: слабые train-кандидаты больше не скрывают OOS, а тестируются и пишутся в report.
- Детали: reports/MECHANICS_WIRING_STATUS_2026_07_01.md. Следующий gate: нормальный rolling WF только на реворкнутой цепочке.

## ДОБАВЛЕНО 2026-07-01 (первые цифры механики + пред-регистрация, Claude)
- Codex встроил механику (portfolio_engine pending-limit, IRV4 level_entry+retest_quality). ПЕРВЫЙ ПОЗИТИВ: IRV4 base PF0.691(минус) -> +limit 1.25 -> +полная цепочка 2.52 (240d ADA/DOGE/SUI, 22 сделки). Фикс позднего входа ПОДТВЕРЖДЁН. SpikeFade провалил fee-stress -> НЕ canary (дисциплина работает).
- КРАСНЫЕ ФЛАГИ: N мал (22), символ-зависимость (эдж несут SUI+DOGE, LINK/SOL минус), 240d=одно окно. Rolling gate считается.
- ПРЕД-РЕГИСТРАЦИЯ критериев PASS: reports/INPLAY_V4_GATE_PREREG_2026_07_01.md (≥3/4 фолдов+, медиана>0, peak-gate, N≥40, fee-stress, + cross-symbol на ДРУГИХ mid-caps). DeepSeek — ПОСЛЕ цифр, не вместо.

## ДОБАВЛЕНО 2026-07-01 (InPlay V4 gate ВЕРДИКТ + телеграм-аудит, Claude)
- InPlay V4 mechanics gate: FAIL по пред-регистрации. OOS 4 фолда: +0.62R(9tr)/+0.54R(6tr)/-0.26R(1tr!)/-0.03R(5tr); total +0.87R/21tr. oos_selector passes=False (unstable_frac_pos_0.50: только 2/4 фолда+). Причина провала = НИЗКАЯ ЧАСТОТА (fold3=1 сделка), не отрицательный эдж.
- ПОТЕНЦИАЛ честно: OOS ~+0.4..1.3%/год (risk 0.3-1%), smoke ~+1..4%/год; красные периоды ~50% в OOS. Частота ~1 сделка/11 дней. Это НЕ зарабатывающий рукав (для сравнения Alpaca v38 ~22-28%/год, 1-2 красных мес). Фикс позднего входа реален, но нога слишком редкая.
- ТЕЛЕГРАМ-АУДИТ: логика digest (proof_of_life.py/tg_daily_digest.py) ЧИТАЕТ live-heartbeat -> при запуске на сервере данные СВЕЖИЕ/верные. НО закоммиченные reports/PROOF_OF_LIFE_*.txt СТАРЫЕ (17-25 июня: regime=bull_trend, flat x0.3/ivb1 x0.25/att1 shadow) — противоречат текущему (bear_chop, att1 x0.10). Это устаревшие артефакты в репо, НЕ то что шлёт бот. Alpaca-TG = PAPER/dry-run телеметрия (не live-доход) -> метить явно. Фикс: gitignore/refresh stale-снапшотов + ярлык paper.

## ДОБАВЛЕНО 2026-07-01 (TG root-cause + next steps, Claude)
- TG BUG root-cause: proof_of_life._maybe_refresh_snapshot читает runtime/bot_heartbeat.json, а в mirror оно в runtime/live_mirror/bot_heartbeat.json -> refresh падает -> stale SERVER_SNAPSHOT_latest.json (15июн bull_trend). Свежак есть в runtime/live_mirror/operator/operator_snapshot.json (bear_chop 01июл). Фикс: fallback-пути + проверка на сервере + re-export + метка paper для Alpaca-TG.
- InPlay FAIL = низкая частота (не логика). План: расширить юниверс 7-8 mid-caps + OOS-свип min_quality; вписать+гейтить ARF2/ASB2/ACB1 (пила ещё НЕ тестировалась с тех!); приоритет H4/liquidity (частые механич.) + Alpaca. См. reports/NEXT_STEPS_2026_07_01.md

## ДОБАВЛЕНО 2026-07-01 PM (Codex — proof fix + research queue)
- Реализован TG/proof stale fix: `scripts/proof_of_life.py` теперь проверяет `runtime/live_mirror/bot_heartbeat.json` и `runtime/live_mirror/operator/operator_snapshot.json`; generated `PROOF_OF_LIFE_*` и `SERVER_SNAPSHOT_latest.*` удалены из tracked git и добавлены в `.gitignore`.
- Проверка после фикса: proof показывает свежий live state `bear_chop`, `dry_run=False`, `open_trades=0`, live-risk только `att1 x0.10`; старый `bull_trend/flat/ivb1` больше не берётся из committed stale snapshot.
- Зафиксирован отчёт: reports/SESSION_STATUS_2026_07_01_PM.md.
- InPlay V4 full-grid mechanics gate запущен в `screen irv4_mech_gate_full_20260701`; лог `logs/manual_research/irv4_mechanics_gate_full_20260701.log`. Это проверяет, не был ли предыдущий 12-combo gate слишком узким.
- H4 cascade: локально нет реального `runtime/liquidations/bybit_liquidations.jsonl`/OI/funding series; proxy mid-cap test (`SOL/DOGE/AVAX/LINK/ADA`) FAIL PF0.26, значит простой price/volume fade нельзя считать H4-эджем. Настоящий H4 gate нужен на серверных реальных liq/OI/funding данных.

## ДОБАВЛЕНО 2026-07-01 (код-ревью Codex + H4 real-data спек, Claude)
- КОД-РЕВЮ portfolio_engine limit-fill: ЧЕСТНО, без lookahead (signal_i<i, fill только если bar реально дошёл до лимита, expiry, SL-first). IRV4 корректно ставит entry_order_type=limit из plan_level_entry, уважает chase-guard. InPlay FAIL = настоящий, не артефакт.
- H4 proxy упал (PF 0.26) -> подтверждает: наивный фейд спайка = минус. Реальный H4 требует данных (liq/OI/funding по mid-caps) -> reports/H4_REAL_DATA_TEST_SPEC_2026_07_01.md (сбор + прогон через cascade_reversal+level_entry+slippage(inplay)+wf_folds+oos_selector, пре-регистр критерии). H4 приоритетнее расширения InPlay (событийная = чаще).

## ДОБАВЛЕНО 2026-07-01 (preflight_check + range/bounce runbook, Claude)
- bot/preflight_check.py ГОТОВ под тестами (tests/test_preflight_check.py 6 зелёных; фундамент 227). Дешёвый GO/NO-GO ПЕРЕД дорогим OOS-gate: частота (N total, per-fold), покрытие символов. Ловит InPlay-проблему ЗАРАНЕЕ (21 сделка/тонкий фолд -> NO-GO). Не даёт гонять пустые тесты.
- RUNBOOK range/bounce: reports/RANGE_BOUNCE_EXECUTION_RUNBOOK_2026_07_01.md — порядок: ARF2 на общий контракт -> pre-flight 4 сторон (ARF2_short/ASB2_long/ACB1_long/ACB1_short) на широком юниверсе (7-8 mid-caps) -> OOS gate ТОЛЬКО для GO -> champion_challenger. Side-split, честные издержки, пре-регистр критерии. Учтено всё, пустых тестов нет.

## ДОБАВЛЕНО 2026-07-01 (сплит-управление + единые уровни, Claude)
- bot/unified_levels.py (6 тестов): ОДИН вызов -> ВСЕ типы уровней (horizontal/sloped/hvn/flip/liquidity/round) с тегами + nearest support/resistance по всем типам. Ответ на «все стратегии учитывают все уровни»: любая нога берёт полную картину, а не свой кусок. Codex: подключить как level-source (ARF2 первым).
- bot/sleeve_registry.py (6 тестов): (стратегия x сторона) = АТОМАРНАЯ единица. sleeve_id, group_by_sleeve, sleeve_health (side-specific!), SleeveRegistry (risk/stage per side), apply_lifecycle (демоут ТОЛЬКО плохой стороны). Демо: arf2:long healthy / arf2:short halt -> шорт стопаем, лонг живёт. Bidirectional-PF больше не основание для live. Фундамент 239.

## ДОБАВЛЕНО 2026-07-01 (DeepSeek hardening — Codex)
- Уточнение после внешней критики: preflight теперь проверяет не только частоту/coverage, но и дешёвый quality sanity, если dry-run records содержат `r/pnl_r/net_r`: `quality_pf < 0.80` блокирует дорогой OOS, `0.80..1.00` помечается caution. Это снижает риск гонять частый, но шумовой рукав.
- unified_levels усилен: horizontal/flip/HVN/channel считаются по свежему lookback-окну, добавлен `max_age_bars`, merge близких уровней в одну зону с приоритетом источника, `best_level()` для стратегий, `include_liquidity` можно выключить (текущая liquidity = recent extreme, не полноценная heatmap).
- RANGE_BOUNCE_RUNBOOK обновлён: ARF2 old/new A/B перед миграцией, sequential filter analysis перед preflight/OOS, low-frequency рукава отделяются от high-frequency range-пакета. H4_SPEC обновлён: data-quality gate, 1m/5m liq aggregation, OI/funding caveats, hybrid execution, crash-day stress.
- Verification: helper-suite `123 passed`.

## ДОБАВЛЕНО 2026-07-01 (ARF2 флаговый wiring — Codex)
- `strategies/alt_resistance_fade_v2.py` получил research-only флаги для общего контракта: `ARF2_USE_UNIFIED_LEVELS`, `ARF2_USE_RANGE_FILTER`, `ARF2_USE_RETEST_QUALITY`, `ARF2_USE_ELDER_FILTER`, `ARF2_USE_LEVEL_ENTRY`. Все OFF по умолчанию, baseline не меняется.
- `ARF2_USE_LEVEL_ENTRY=1` строит limit-at-level сигнал с `entry_order_type="limit"` и `limit_validity_bars`; добавлен тест. Это открывает OLD vs NEW A/B без live-risk.
- Verification: ARF2+helper focused suite `53 passed`. Отчёт: `reports/ARF2_WIRING_STATUS_2026_07_01.md`.

## ДОБАВЛЕНО 2026-07-02 (оценка ночной работы Codex, Claude)
- ARF2 helper-chain: вписан КОРРЕКТНО и БЕЗОПАСНО (за флагами use_unified_levels/retest_quality/level_entry=False по умолчанию, на общем контракте, использует мои модули). Вердикт NO-GO честный: unified_levels починил ТИШИНУ (частота 5->39->57), но не прибыльность; tiny-N "3 сделки PF 1.99" правильно НЕ промоутят. Ключевой инсайт Codex ВЕРНЫЙ: пиле нужна смена логики (fade ТОЛЬКО после exhaustion/failed-breakout, не просто "у сопротивления") — совпадает с моим давним тезисом (fade у уровня в не-range режет пила).
- unified_levels/sleeve preflight: hardened (de72391, 5229bf1) — работает как задумано (дал частоту).
- ФЛАГ по ATT1 r068 (live-рукав): config взял pocket r068 (284 tr, +19.17R, PF 1.30, DD 6.61) как "360d replay" — это ОДНО окно / selected pocket, НЕ показан проход rolling-OOS (wf_folds/oos_selector). При risk 0.10 canary это приемлемо (breaker+expiry, малый риск), НО перед ЛЮБЫМ повышением риска ATT1 r068 обязан пройти тот же OOS-гейт, что и все. Записать в go/no-go.
- InPlay V4 wide gate идёт: train 39tr +3.48R PF1.99 (in-sample!), level_entry реально используется (проверено в trades). Ждём OOS-фолды. Частота выросла -> preflight скорее GO.

## ДОБАВЛЕНО 2026-07-02 (smart_grid — частый механич. рукав, Claude)
- bot/smart_grid.py (5 тестов; фундамент 244): режим-осознанный сеточник, «умнее Велеса». Активен ТОЛЬКО в подтверждённом range (classify_channel flat + regime_hmm не high_vol), сетка привязана к реальному каналу [lower,upper], KILL-SWITCH при пробое канала/смене режима -> halt_and_flatten (не держит мешок в тренде — главная беда обычных сеток). Частый рукав -> «торгует каждый день» в боковике. Механика (осцилляция), не прогноз. Требует OOS-гейт как все.
- ВИДЕНИЕ AI-supervised портфель: пьесы есть (decision_bus/edge_monitor/regime_hmm/champion_challenger/sleeve_registry/adaptive_context). Не хватает ОРКЕСТРАТОРА-цикла: читает bus -> regime-гейт+risk_scalar -> edge_monitor -> promote/demote -> аллокация. ВАЖНО: ИИ крутит РИСК/РЕЖИМ/ЖИЗН.ЦИКЛ В РЕЛЬСАХ, НЕ свободную live-оптимизацию параметров (=оверфит). Это следующий интеграционный слой (Codex вписывает в live-loop).

## ДОБАВЛЕНО 2026-07-02 (статус wiring — пауза стройки, Claude)
- ЧЕСТНО: 24 модуля построено, вписаны в ноги ТОЛЬКО 2 (inplay_retest_v4, ARF2)+движок limit. ~20 модулей провалидированы на юнитах, но НЕ в торговле/управлении. РЕШЕНИЕ: стройку на паузу, приоритет wiring+gate. Backlog: reports/MODULE_WIRING_STATUS_2026_07_02.md. Приоритет: smart_grid backtest -> InPlay wide gate вердикт -> ARF2 exhaustion-логика -> liquidity/H4 -> orchestrator. Правило: не строить новое, пока построенное не вписано и не прогнано.

## ДОБАВЛЕНО 2026-07-02 (InPlay wide gate — маргинальный PASS, Claude)
- InPlay V4 wide gate (7 mid-caps): gate вернул passes=True (robust_plateau), НО по НАШЕЙ пре-регистрации это НЕ чистый pass: total 36<40, fold4=2 сделки/fold3=3 (<8/фолд), робастность -0.068<0, fold1 PF1.03=шум. Потенциал ~0.4-1.2%/год. ВЕРДИКТ Claude: -> SHADOW (paper) накапливать сделки, НЕ canary.
- ФИКС Codex: gate-скрипт oos_selector мягче нашей пре-регистрации (пропускает тонкие фолды 2-3 сделки). Ужесточить min_trades_per_fold>=8 и min_trades_total>=40, отклонять робастность<=0. Иначе штампует пустышки как PASS.
- Стройка на паузе (built>>validated). Следующее: smart_grid backtest, InPlay->shadow, ARF2 exhaustion-логика. Новые модули НЕ пишем.

## ДОБАВЛЕНО 2026-07-02 (research_orchestrator — недельный ИИ-ревью, Claude)
- bot/research_orchestrator.py (6 тестов; фундамент 250): реализует видение «постоянный теневой поиск + ИИ под капотом + предложения раз в неделю». weekly_review компонует oos_selector+edge_monitor+champion_challenger+preflight -> Proposal: действия по рукавам (PROMOTE/DEMOTE/HOLD), ранг новых кандидатов (GATE_PASS/NO), shadow-retest-очередь. format_proposal -> человекочитаемо (для TG). РЕЛЬС: только ПРЕДЛАГАЕТ, человек одобряет; НЕ крутит риск/параметры сам. Демо: PROMOTE att1(healthy canary), DEMOTE arf2(degraded), smart_grid GATE_PASS.
- Это капстоун управляющего слоя (не новый эдж). Codex: гонять раз в неделю (scheduled), слать Proposal в TG на аппрув.

## ДОБАВЛЕНО 2026-07-02 (smart_grid v2 fee-aware, Claude)
- bot/smart_grid.py ПЕРЕПИСАН под провал smoke (PF0.34/DD86). Два фикса: (1) STRONG-FLAT гейт через range_filter.is_range (не просто slope-flat), (2) FEE-AWARE шаг: grid step >= fee_survival_mult*round-trip-fee, иначе fee_infeasible->idle (сжимает n_levels пока шаг не перекроет комиссию). + kill-switch на пробой/high_vol. Тесты 7 зелёных (фундамент ~252). Демо: strong flat low fee -> grid 10 ур; high fee -> отказ.
- НЕ доказан: нужен RE-TEST. Адаптер strategies/smart_grid.py должен честно реализовать МУЛЬТИ-ордер грид + kill-flatten + fee-aware шаг (v1 адаптер, вероятно, гридил в шум/тренд). Честно: сетки — тяжёлый эдж; ARF2 exhaustion вероятно выше по шансам.
- ПОЗИТИВНОГО портфеля пока НЕТ: live только ATT1 short tiny canary (ждёт). Реальный первый плюс = Alpaca v38 (paper-доказан), ждёт $500.

## ДОБАВЛЕНО 2026-07-02 (EDGE_HUNT — офенс по нашим козырям, Claude)
- Разворот к активной охоте: дисциплина=не врать себе, НЕ перестраховка. Рабочий эдж не публичен -> ищем на СВОИХ данных. Козыри: (1) свой liq/OI/funding поток (H4 триггерный — НЕ тестирован на реале, #1 фронтир), (2) FX/CFD структурные ноги (не строили: XAU sweep, London/NY breakout-retest, session range, trend-pullback), (3) ИИ-майнер гипотез из decision_bus (в рельсах->OOS), (4) cross-exchange/basis. План: reports/EDGE_HUNT_2026_07_02.md. Приоритет: A H4 real-data, B FX native demo, C ИИ-майнер, D ATT1 strict OOS+символы.

## ДОБАВЛЕНО 2026-07-02 (FX native пакет, Claude)
- bot/fx_setups.py (7 тестов; фундамент 259): 4 родных FX-сетапа (session_range_fade, round_level_sweep, session_breakout_retest, trend_pullback) — композит наших технологий, сплит long/short, под свипы тысяч вариаций, все с news_session_filter. НЕ порт крипты. Данные бесплатные (demo). Спек: reports/FX_NATIVE_PACKAGE_2026_07_02.md.
- Конвейер перебора: свип (символы×сторона×сессии×параметры) -> preflight -> wf_folds -> oos_selector. Offense: пробуем много/быстро, отбор по OOS. XAU round-sweep — топ-интерес.

## ОБНОВЛЕНО 2026-07-02 (smart_grid side-split, Claude)
- bot/smart_grid.py: добавлен параметр side (long=только биды/накопление лонга на дне; short=только аски; both). Теперь сетка делится long-only/short-only как все рукава -> отдельная статистика/гейт по стороне. 9 тестов зелёных (фундамент 261). FX/CFD: работает (тот же OHLC-контракт). Стабильные мажоры+золото = лучший дом для сетки (чистые ranges, тайт спреды -> fee-aware гейт проходит легче, каждая сторона свипается отдельно).

## ДОБАВЛЕНО 2026-07-02 (range_scanner + ATT1 позитив, Claude)
- bot/range_scanner.py (6 тестов; фундамент 267): сканер range-качества инструментов -> сетка/range-ноги работают ТОЛЬКО на лучших флетах (недостающий #1 для сетки: подбор правильных монет). scan/best_ranging: тренд->0, хаос->не tradeable, чистый флет->топ.
- ATT1 REVALIDATE = сильнейший позитив: 4/12 combos стабильно (r001-r004: 410-440 сделок, +32..36R, PF~1.31, DD~4.5R, 1-2 красных мес). ПЛАТО параметров (не один pocket). Потенциал ~10-25%/год (risk 0.3-0.75%). НО это ревалидация, НЕ rolling-OOS. Следующий гейт: strict rolling-OOS -> если держит, обосновать повышение риска ATT1 выше 0.10. Это может стать ПЕРВЫМ реальным earner (крипта, не Alpaca).
- smart_grid v2 smoke -12.62 (Codex, до side-split): безопаснее, но минус -> research-only. Фикс: range_scanner (правильные инструменты) + возможно trailing/inventory-cap. Дом сетки — FX мажоры+золото.

## ДОБАВЛЕНО 2026-07-02 (risk_manager — умный гибкий риск, Claude)
- bot/risk_manager.py (9 тестов; фундамент 276): адаптивный риск = base * regime * health * drawdown * vol, clamp[0,hard_cap]. АНТИ-МАРТИНГЕЙЛ: в просадке/degraded/high_vol РЕЖЕМ, не наращиваем. Блок в high_vol и halt. Общий для ATT1+сетки+портфеля. Композит regime_hmm+edge_monitor+position_sizing, в рельсах.
- Codex: обернуть sizing каждого рукава smart_risk; ATT1 при повышении риска после rolling-OOS использовать smart_risk (гибко), не фиксированный процент.

## ДОБАВЛЕНО 2026-07-02 (ATT1 short rolling-OOS пре-регистрация, Claude)
- ATT1 revalidate 12/12 PASS. SIDE-РАЗРЕЗ (наш сплит сработал): short +30.19R PF1.52 folds PASS = кандидат; long +6.48R PF1.12 = one-window hero -> НА СКАМЕЙКУ (retest-очередь). Без сплита вывели бы дохлый long.
- Пре-регистрация strict rolling-OOS ATT1 short + план разгона риска через smart_risk: reports/ATT1_SHORT_ROLLING_OOS_PREREG_2026_07_02.md. Пороги: >=3/4 фолда, медиана>0, робастность>0, N>=40/>=8-фолд, fee-stress, DD<=6R. PASS -> пошаговый разгон 0.10->0.25->0.5->0.75 через smart_risk, каждый шаг подтверждается live healthy (edge_monitor), анти-мартингейл, hard_cap<=1%.
- Стройка на паузе (25 модулей, 276 тестов). Следующее — прогоны Codex + мой честный разбор, не новый код.

## ДОБАВЛЕНО 2026-07-02 (fx_harness — FX разблокирован, Claude)
- bot/fx_harness.py (6 тестов; фундамент 282): бэктест-харнесс для fx_setups. Прогоняет сетап по FX-барам, открывает трейд с fixed-R (SL=sl_atr*ATR, TP=tp_rr*R), резолвит на ПОСЛЕДУЮЩИХ барах (SL-first), комиссии в R, cooldown/без перехлёста. Выдаёт trades -> wf_folds -> oos_selector. Причинно. Единственный блокер FX (harness) СНЯТ.
- ПЕРЕПРИОРИТЕТ: FX больше НЕ в конце очереди. Это ПАРАЛЛЕЛЬНЫЙ трек (бесплатные demo-данные, свой харнесс, не конкурирует с ATT1 за крипто-компьют). Codex: подать реальные FX-данные (Dukascopy/yfinance/OANDA demo) в fx_harness, свипать XAU round_sweep + session_breakout + range_fade + smart_grid(мажоры) через preflight->wf_folds->oos_selector.

## ДОБАВЛЕНО 2026-07-02 (ВЕХА: ATT1 short r001 прошёл строгий барьер, Claude)
- ATT1 short r001 = ПЕРВЫЙ честно-валидированный крипто-эдж: strict folds 4/4, 239-307 сделок, peak 2.35 (не hero), fee-stress выживает (10/5bps: +16.5R PF1.21), 2 красных мес. Потенциал ~14%/год@0.5%, ~21%@0.75%, DD~3-5%.
- РЕШЕНИЕ (reports/ATT1_R001_MIGRATION_DECISION_2026_07_02.md): мигрировать ATT1 canary на r001-геометрию, риск ОСТАВИТЬ 0.10 (не поднимать при миграции) -> 10-20 live healthy сделок -> разгон через smart_risk (0.10->0.25->0.5->0.75), анти-мартингейл. Claude готовит config-спек, Codex подставляет точные r001 params + деплой после OK владельца.
- Параллельно: FX (fx_harness real-data, XAU/session первыми) + ARF2 exhaustion.

## ДОБАВЛЕНО 2026-07-02 (failed_breakout — ARF2 exhaustion фикс, Claude)
- bot/failed_breakout.py (6 тестов; фундамент 288): детектор несостоявшегося пробоя. Цена вышла ЗА уровень (close beyond) и НЕ удержалась (reclaim обратно в range за event_window) -> фейд. Мульти-бар (не 1-бар свип). Опц. vol-fade. Сплит: fail-up->short, fail-down->long. НЕ фейдит удержавшийся пробой (тест подтвердил). Это правильная логика для ARF2/пилы (фейд после провала пробоя, не «просто у уровня»).
- Codex: перевести ARF2 на failed_breakout+range_filter+level_entry вместо «fade at resistance» -> preflight -> gate. Это следующий крипто-кандидат после ATT1 r001.

## ДОБАВЛЕНО 2026-07-02 (разбор ARF2+FX + мета-инсайт про частоту, Claude)
- ATT1 r001 миграция: чисто, риск 0.10 держим (правильно). Ждёт short-наклонку. ЕДИНСТВЕННОЕ около денег.
- ARF2 failed_breakout: NO-GO, но пульс есть. plain 177 сделок +6.02R PF1.05, 2/4 фолда красные. Инсайты Codex ВЕРНЫЕ: (1) level_entry ВРЕДИТ failed-breakout (−65R) — логично: на провале пробоя входим на reclaim СРАЗУ, а не лимиткой у уровня; level_entry для РЕТЕСТОВ, не для reclaim. (2) range_filter слишком строг для этого события. (3) DOGE/XRP/ONDO несут (symbol-selection риск). Фикс: убрать level_entry для этого сетапа, ослабить range-гейт; но эдж тонкий -> низкий приоритет.
- FX smoke: XAUUSD round_level_sweep 4 сделки +0.94R PF1.37 (пульс на золоте!), остальное 0 сделок (round_sweep/session_breakout РЕДКИЕ на 60d M5). NO-GO по частоте.
- МЕТА-ИНСАЙТ: наш ГЛАВНЫЙ повторяющийся барьер = ЧАСТОТА/fold-стабильность (не lookahead, не издержки). Редкие сетапы не набирают N для OOS (InPlay, ARF2, round_sweep, grid — все упёрлись в это). Рычаги: (a) ЧАСТЫЕ сетапы приоритетнее редких (session_range_fade, trend_pullback, grid > round_sweep, breakout); (b) шире юниверс; (c) больше/длиннее данных (60d M5 мало); (d) ослаблять гейты, но OOS-тестить.
- FX-ГАЙД Codex: свипать в первую очередь session_range_fade + trend_pullback (частые) на БОЛЬШЕЙ истории + XAU (показал пульс); редкие round_sweep/breakout — вторично.

## ДОБАВЛЕНО 2026-07-02 (structure_break BOS/CHoCH + FX-свип разбор, Claude)
- bot/structure_break.py (6 тестов; фундамент 294): чистый детектор слома структуры. BOS=пробой свинга ПО тренду (продолжение), CHoCH=пробой ПРОТИВ тренда (разворот). Из pivot_highs/lows. Сплит long/short. Ранее слом структуры был разрозненно в choch_v1/breakdown — теперь единый проверяемый контракт. Частый паттерн -> против проблемы частоты. Codex: построить BOS/CHoCH-ногу + gate.
- FX bg-свип разбор: session_range_fade на XAU ЧАСТЫЙ (285 сделок) но ТЕРЯЕТ (-117R PF0.51, золото ломает range). round_level_sweep XAU: ПУЛЬС (tp2/sl1: +3.57R PF1.49, 3/3 фолда+) но 12 сделок (мало N). Урок: нужен частый И с эджем; частый без эджа теряет быстрее. session_breakout=0 сигналов.
- FX-вывод: range_fade на золоте -> NO. round_sweep -> пульс, добрать N (больше данных/символов). Гнать BOS/CHoCH + trend_pullback на FX (частые+трендовые).

## ДОБАВЛЕНО 2026-07-02 (structure_break частота на крипте, Claude)
- structure_break прогнан на РЕАЛЬНОЙ крипте (60m): BOS/CHoCH сигнал на ~26-30% баров (BTC 216 bos+85 choch/1192; SOL/LINK/ADA аналогично), long/short сбалансированы. ЧАСТЫЙ (vs ATT1/InPlay редкие) -> ответ на проблему частоты. Работает на крипте И FX (один OHLC-контракт). Оговорка: 28% сырых многовато -> фильтр (regime_hmm/retest_quality/cooldown) иначе оверрейд. Codex: BOS/CHoCH-нога с фильтром -> preflight -> gate на крипто-mid-caps И FX.

## ДОБАВЛЕНО 2026-07-02 (КОРРЕКЦИЯ structure_break свипа, Claude)
- ПРОБЛЕМА: scripts/run_structure_break_diagnostic.py гоняет сетку event/side/RR/SL/hold/buffer БЕЗ фильтра/cooldown -> тестирует СЫРОЙ (оверрейд) сигнал, который мы знаем минусовой. 4ч прогон предрасположен к NO-GO.
- ДАННЫЕ (реальная крипта 60m, sl1/tp2): RAW BTC -39R/SOL -14R/ADA +53.5R. С cooldown=10: BTC -39->-2R, ADA expectancy +0.28->+0.52R (меньше сделок, выше качество). Cooldown = ключевой рычаг против 28%-частоты.
- КОРРЕКЦИЯ Codex: добавить в сетку свипа cooldown_bars {0,5,10,20} (обязательно) + per-symbol отчёт (символ-зависимость огромная: ADA+, BTC/SOL-) + cross-symbol робастность в гейте (не черри-пик ADA). Опц. regime-фильтр. БЕЗ cooldown свип = пустой.

## ДОБАВЛЕНО 2026-07-02 PM (разбор short-bias + режимная оговорка, Claude)
- Codex: crypto BOS long крупно минусовой -> остановил (верно, не жёг время). FX BOS/CHoCH пакет no-go, но XAU BOS short 60d = карман (PF 1.5-2.8, +13..24R, 20-60 сделок). Лучший новый след, но 1 инструмент + короткая история.
- Claude независимая проверка (крипта cooldown=10): short чуть лучше на 3/4, НО ДОМИНИРУЕТ СИМВОЛ, не сторона: ADA + с обеих, BTC/SOL -, LINK long(+4)>short(+1.4). Плюс режимный крен (short лучше в падении). Вывод: «short-only» НЕ чистый ответ; это symbol×side×regime.
- РИСКИ для Codex: (1) short-эджи вероятно bear_chop-зависимы -> long-history свип должен дать per-period/per-year разрез (выживает ли в bull-ногах?); если bear-only -> нужен regime_hmm-гейт (выключать в bull) + correlation-cap (несколько short-рукавов вместе сольются в bull-развороте). (2) не резать long целиком -> держать per-symbol×side гранулярность, отбор по cross-symbol робастности, не «short-only». (3) XAU short 60d -> не радоваться карману; PASS = стабильность на 876d+ и per-period.

## ДОБАВЛЕНО 2026-07-03 (ARF2 failed-breakout кандидат #2 + пре-регистрация, Claude)
- Codex: ARF2 failed_breakout short DOGE/XRP/ONDO = +25.87R PF1.65, fee-stress держит (16bps PF1.41), обе половины+90d+, 3/3 символа. НО символы выбраны после анализа (selection bias).
- Claude OOS-symbol чек: НЕ чистый оверфит (свежие символы слабо+: SOL/ADA/AVAX/SUI+, DOT-), но эдж ТОНЬШЕ +25R. Лучше SpikeFade/InPlay (те вне выборки разваливались).
- Пре-регистрация gate: reports/ARF2_FAILED_BREAKOUT_GATE_PREREG_2026_07_03.md. ГЛАВНОЕ = OOS-СИМВОЛЫ (тот же config на свежем наборе, >=50%+, не 1 символ). + temporal + fee-stress + реалистичный размер (не +25R). PASS -> shadow -> canary + ОБЯЗАТЕЛЬНО regime_hmm-гейт (bear_chop-зависимость) + correlation-cap (ATT1-short+ARF2-short коррелированы).

## ДОБАВЛЕНО 2026-07-03 (план: manual gate -> dynamic live selection, Claude)
- Разделение: gate по OOS-символам = проверка ОБОБЩЕНИЯ (фикс. свежий набор, манульно). Live = ДИНАМИЧЕСКИЙ symbol-agnostic отбор (сканер по УСЛОВИЮ, не список монет). Примитив есть — range_scanner; для failed-breakout/структуры сделать аналог КОГДА эдж подтвердится на OOS (не раньше — преждевременно).
- Порядок ввода: ATT1 short (live) -> ARF2 (gate->canary, ~сутки если OOS держит) -> range/пила блок (ASB2/ACB1/ARF2-split + dynamic range_scanner = ЧАСТОТА) -> пробои через confirm+retest+regime -> InPlay (редкий, позже) -> FX native (2-3 недели).
- Реалистично «3 рукава» на след. неделе = ATT1 + ARF2(если PASS) + Alpaca($500 владелец). FX догоняет позже.

## ДОБАВЛЕНО 2026-07-03 (блупринт живой управляющей петли, Claude)
- reports/LIVE_MANAGEMENT_LOOP_BLUEPRINT_2026_07_03.md: как собрать динамику+ИИ-надзор в прод. Вход рукава = динамич. отбор символов (scanner по условию, НЕ хардкод) -> сигнал -> regime/конфлюэнс гейты -> level_entry -> smart_risk -> exposure-cap -> decision_bus. Фон: edge_monitor (throttle/halt). Еженедельно: research_orchestrator Proposal в TG на аппрув владельца. Не деградирует (динамика+decay-монитор+ротация), всё в рельсах.
- ЧЕСТНО: управляющий слой ПРОТЕСТИРОВАН (294 теста), но в живой петле НЕ крутится. Вписывать по мере live-рукавов, начиная с ARF2 (динамич. символы, не фикс DOGE/XRP/ONDO).

## ПРИНЦИП РАЗВИТИЯ (зафиксировано 2026-07-03, Claude) — против искажения/оверфита
- Технологии сейчас НЕ подключены к live -> сломать не могут. Вписывание: ОДИН рукав за раз, за флагом, с тестами, деплой после OK владельца, canary tiny. 294 теста = регрессия-сетка.
- Отбор монет = АВТОМАТ+ДИНАМИКА (сканер по условию, не список). ИИ-аппрув = на уровне СТРАТЕГИИ раз/неделю (не по монете). Частое/объективное — автомат; редкое/высокоставочное — человек.
- НЕ включать всё разом (исказит картину, оверфит). Метод: (1) одно изменение за раз с A/B-замером; (2) decision_bus для АТРИБУЦИИ (что реально помогает); (3) технология ЗАСЛУЖИВАЕТ включение улучшением OOS/live, иначе в ящике; (4) смещение к ПРОСТОТЕ (меньше активных фильтров = робастнее). 26 модулей = ящик инструментов, берём выборочно под рукав, НЕ "включить всё".

## ДОБАВЛЕНО 2026-07-03 (МАСТЕР-КАРТА технологий + план фаз, Claude)
- reports/MASTER_MAP_AND_PLAN_2026_07_03.md: карта «зачем каждая технология» (find->select->execute->size->prove->monitor->improve, ни одна не лишняя) + 4 фазы: Ф1 первые рукава (ATT1/ARF2/Alpaca) -> Ф2 частота (range блок+dynamic scanner) -> Ф3 сборка портфеля+живая петля -> Ф4 умное улучшение технологиями (A/B + decision_bus атрибуция + research_orchestrator еженедельно, в рельсах). НЕ отказываемся от технологий — берём выборочно, включаем по результату. ИИ-анализ бота = edge_monitor(онлайн)+research_orchestrator(еженедельно).

## ДОБАВЛЕНО 2026-07-03 (ARF2 OOS-symbol gate — NO-GO, Codex)
- Пре-регистрированный главный риск ARF2 подтвердился: символы DOGE/XRP/ONDO были выбраны после анализа. OOS-symbol gate на независимом наборе `BTC/SOL/LINK/ADA/AVAX/DOT/SUI/LTC/ATOM/BNB/BCH/XLM/1000PEPE/HYPE/TAO` провалился.
- Результат OOS: `failed_breakout_short` 132 сделки, -15.48R, PF0.83; `failed_breakout_volfade_short` 112 сделок, -11.62R, PF0.85. При этом selected DOGE/XRP/ONDO оставались +25.87R PF1.65. Вывод: focused результат selection-inflated, в canary/live НЕ пускать.
- ARF2 failed-breakout возвращается в research. Следующий ремонт только через symbol-agnostic динамический scanner/gate + regime split + quality score, потом broad preflight -> OOS. Не использовать `level_entry` для reclaim-entry failed-breakout.
- Отчёт: reports/ARF2_FAILED_BREAKOUT_OOS_SYMBOL_VERDICT_2026_07_03.md.

## ДОБАВЛЕНО 2026-07-03 (ARF2 OOS-symbol gate FAIL — победа процесса, Claude)
- ARF2 failed-breakout: выбранные DOGE/XRP/ONDO +25.87R PF1.65, НО независимые OOS-символы -15.48R PF0.83 (volfade -11.62R). SELECTION BIAS пойман gate'ом ДО денег. ARF2 НЕ в live/canary. Ни доллара не слито на раздутой цифре. Это ровно зачем нужен OOS-symbol gate.
- Портфель: live только ATT1 r001 x0.10 (ждёт наклонку). Второй крипто-рукав теперь от crypto_structure_break_cd_gate или следующего range/bounce ремонта, НЕ от старого ARF2.

## ДОБАВЛЕНО 2026-07-03 (новый чат: аудит перед разбором гейтов, Claude)
- Гейты crypto_structure_break_cd_gate_20260703 / fx_native_gate_20260703 созданы 09:33-09:34, диры ПУСТЫЕ = в полёте у Codex. Разбор — как только появятся файлы. Также пустые: xau_structure_break_long_20260703, structure_break_crypto_short_20260703, structure_break_crypto_cooldown_overnight_20260702 (Codex: подтвердить — бегут или умерли).
- XAU round_level_sweep LONG (37 сделок, 876d H1) = NO-GO: ВСЕ 18 комбо минусовые (лучшее -2.83R PF0.89), short ещё хуже (-6..-10R PF0.26-0.56). Вчерашний «пульс» (+3.57R на 12 сделках) умер при добавлении N — классика tiny-N. round_sweep ЗАКРЫТ по обеим сторонам.
- FX BOS/CHoCH cooldown overnight: вся сетка минусовая (лучшее -0.86R PF0.98) — подтверждает no-go. FX-надежда остаётся только trend_pullback/session-сетапы в бегущем fx_native_gate.
- АУДИТ ГЕЙТ-МАШИНЕРИИ: (1) oos_selector строгий путь ужесточён ВЕРНО (gate-скрипт: 40 total/8 per fold, robustness<=0 -> reject, median<=0 -> reject) — фикс от 07-02 применён. (2) НО run_structure_break_diagnostic.py = IN-SAMPLE свип (cooldown-грид+per-symbol+preflight 40/8/3 есть, wf_folds/oos_selector НЕТ); run_fx_native_harness.py = грубые 4 хроно-фолда без purge/embargo. => Сегодняшние «gate»-прогоны считать СКРИНИНГОМ: их PASS не даёт canary, а даёт билет на строгий wf_folds+oos_selector+OOS-symbol набор (как ARF2). Не переименовывать скрининг в гейт.
- ATT1 r001 canary config проверен: risk 0.10, short-only, breaker+expiry 2026-07-20, все непруфнутые рукава занулены — корректно. Live-статус из локального репо НЕ верифицируем (trades.db устарел, журнал на сервере). Codex: прислать журнал/скрин live-канарейки в следующем статусе.

## ДОБАВЛЕНО 2026-07-03 (аудит перед вторым рукавом, Claude)
- ТЕСТЫ ВЕРИФИЦИРОВАНЫ: 726 passed, 0 реальных красных (3 «падения» trade_startup_recovery/trade_sync = отсутствие websockets в песочнице, после установки зелёные). Исключены из прогона только файлы, требующие данных/env (alpaca backtests, liquidations collector).
- ATT1 LIVE-ПУТЬ ОТАУДИРОВАН, вердикт ЧИСТО: shadow при risk<=0; breaker блокирует вход с TG-алертом; soft-режим режет риск; sizing = ATT1_RISK_MULT x breaker_mult; при ошибке breaker'а fail-safe БЛОК; canary expiry 2026-07-20 жёстко блокирует до ручного продления. Breaker слушает live id att1_trendline_touch (не бэктест-id) — корректно.
- НЮАНС (не баг): ATT1_ALLOW_MINQTY_FALLBACK=True default, cap 1.8x — на мелком счёте эффективный риск сделки может быть ~0.18 вместо 0.10. Codex: замерить долю fallback-входов; если >30% — учитывать при решении о разгоне риска (live-статистика бежит «горячее» номинала).
- Очередь Codex: CODEX_QUEUE_2026_07_03.md (статус пустых гейт-дир, скрининг≠гейт терминология, строгий путь после скрининга, ATT1 журнал+fallback, закрытые направления).

## ДОБАВЛЕНО 2026-07-03 (спек wiring decision_bus+edge_monitor в ATT1, Claude)
- reports/ATT1_DECISION_BUS_EDGE_MONITOR_WIRING_SPEC_2026_07_03.md: канарейка с первого дня пишет атрибуцию (enter/skip с контекстом breaker_mult/minqty_fallback/fallback_stretch, outcome по bus_id от ФАКТИЧЕСКОГО риска) + почасовой edge_monitor (baseline 0.054R = fee-stress 10/5bps, halt=громкий алерт, НЕ авто-стоп — единственный автостоп остаётся breaker). Всё за флагами default 0, rollback=выключить флаги. Codex: реализовать по спеку, тесты обязательны, деплой с флагами 0 -> сутки -> OK владельца -> включить.
- Решение владельца: Alpaca $500 на выходных (копилка/стабилизатор). Фокус разгона = крипта (A) + FX (B). Переделка провалившихся стратегий — ТОЛЬКО через гипотезу+одна технология+A/B на OOS (не наваливать фильтры до розового винрейта — так чуть не пустили ARF2).
- Ожидание: crypto_structure_break_short_screen ~2-3ч, fx_native_gate ~4-6ч. Оговорка к short-screen зафиксирована ранее: short-only после провала long на тех же данных = условность на выборке -> планка выше (cross-symbol, per-period, regime-гейт+corr-cap в live).

## ДОБАВЛЕНО 2026-07-03 (live forensics candle coverage, Codex)
- Свежий пересчёт live-forensics за 45d подтвердил `missing_candles`: 31/41 сделок не реконструируются по `.cache/klines`; range = 20/20 missing, breakdown = 6/11, ATT1 = 3/7, flat = 2/2.
- Серверный cache также не содержит dynamic range symbols: APE/APT/BERA/DASH/DYDX/GALA/JUP/OP/POL/PYTH/RENDER = 0 files. Core symbols есть (ADA/BTC/ETH/DOGE).
- Интерпретация: это не доказывает, что live-бот входил без свечей, но доказывает, что MFE/MAE/live-vs-backtest forensics по range/pila сейчас ненадёжны. Range/pila остаётся risk=0 до candle-coverage/backfill gate: 0% missing по canary symbol set -> 180/360d OOS/additivity -> только потом tiny canary.
- Отчёт: reports/LIVE_FORENSICS_CANDLE_COVERAGE_2026_07_03.md.

## ДОБАВЛЕНО 2026-07-03 (raw structure/FX screening fast-fail, Codex)
- Raw crypto BOS/CHoCH screens stopped early: BOS-long, BOS-short and CHoCH-short all opened with broad large negative expectancy (examples: BOS-long -939R PF0.60, BOS-short -574R PF0.75, CHoCH-short -206R PF0.78). Частота есть, edge нет. Дальше только с quality/regime фильтром, не raw grid.
- Naive FX session_range_fade stopped early: EURUSD 1111 trades, -3061R, PF0.00. FX требует setup audit; текущие trend_pullback/round/session_breakout дали ноль сигналов на первых majors, range_fade даёт частый минус.
- Отчёт: reports/STRUCTURE_AND_FX_SCREENING_FAST_FAIL_2026_07_03.md.

## ДОБАВЛЕНО 2026-07-03 (данные врут раньше стратегий: candle_coverage + cost guard, Claude)
- ВСКРЫТИЕ EURUSD fast-fail: вердикт «PF 0.00 на 1111 сделках» НЕВАЛИДЕН как вердикт по стратегии. Скрининг шёл на M5, где ATR=0.00024 -> стоп 0.8*ATR ~2 пипса -> комиссия в R = 1.78R/сделку. Средний -2.76R = -1R(все стопы) - 1.78R(fee) — точное совпадение. Мы измерили артефакт (таймфрейм x издержки), не рынок. На H1 fee_r=0.38R. Naive fade всё равно слабая гипотеза (XAU честно проиграл при fee_r 0.04R), но EURUSD честного теста НЕ получил.
- bot/candle_coverage.py (9 тестов): P0-гейт полноты данных. coverage/гэпы/flat-бары/дубли/немонотонность; market_closure_gap_bars для FX (уикенд = закрытие, не дыра; крипта 24/7 = дыра). assess_universe -> go/no-go юниверса ДО скрининга. Правило: range/пила не возвращается в live, пока юниверс не пройдёт этот гейт.
- bot/fx_harness.py: + cost_feasibility() (4 теста) — fee_r > 0.25R => run cost_infeasible, PF НЕ читать. Обязателен ПЕРЕД каждым FX-прогоном.
- ЖИВОЙ ЗАМЕР локального FX-кэша (closure-aware): EURUSD/GBPUSD M5 cov 99.8% НО EURUSD flat=14.6%, AUDUSD flat=14.8% (мёртвые бары = источник коллапса ATR); EURJPY cov 98.5%; XAUUSD H1 cov 93.4% (494 гэпа!) — ВСЕ прошлые XAU-вердикты вынесены на дырявых данных. NO-GO оставляем (дыры режут в обе стороны), но после backfill XAU round_sweep/BOS заслуживает ре-скрининга.
- Тесты: 737 passed. Урок дня: у нас уже ДВА случая за сутки, когда «стратегия провалилась» = «данные/издержки врут» (missing_candles live, EURUSD M5). Отсюда порядок: coverage gate + cost guard ВПЕРЕДИ любых новых свипов.

## ДОБАВЛЕНО 2026-07-03 evening (handoff обновлён для переезда)
- Обновлены `reports/CLAUDE_NEW_CHAT_HANDOFF_2026_07_03.md` и `reports/NEW_CHAT_KICKOFF_PROMPT.md`: новый чат стартует с актуальной рамки `data/cost gate first`, а не со старых тем 30 июня.
- Главная инструкция новому чату: не разбирать PF до `candle_coverage` и `cost_feasibility`; live остаётся только ATT1 short r001 risk 0.10; range/pila/FX/XAU пересматривать только после backfill/clean coverage.
- Логистика: если Mac уснёт, локальные jobs могут встать/отвалиться. Вечером первым делом проверять `screen -ls` и логи, а не предполагать, что ночные прогоны реально крутились.

## ДОБАВЛЕНО 2026-07-03 (Codex: coverage/cost gates wired into runners)
- `scripts/run_fx_native_harness.py`: теперь перед прогоном пишет `coverage.csv`, проверяет `candle_coverage`, проверяет `cost_feasibility` по каждой `sl_atr`, и cost-infeasible комбинации НЕ бэктестит (`skip_reason=cost_infeasible`, `fee_r` в summary). Добавлен `--interval-min`: M5 можно честно агрегировать в H1/H4 с сохранением FX timestamps в секундах для session logic.
- `scripts/run_structure_break_diagnostic.py`: теперь пишет `coverage.csv`, фильтрует символы с плохим coverage, а для FX дополнительно пропускает cost-infeasible symbol×sl_atr до симуляции. Crypto structure symbols сегодня coverage-clean, FX M5 — нет.
- Smoke: FX EURUSD M5 `session_range_fade` теперь skip cost-infeasible вместо PF; crypto BTC H1 structure пишет coverage и summary. Тесты P0: `13 passed`.
- Практический вывод: старые запущенные FX M5 скрининги считаются obsolete/diagnostic-only. Новые meaningful FX-прогоны запускать H1/H4 через этот runner.

## ДОБАВЛЕНО 2026-07-03 (карта «видение владельца -> исполнение», Claude)
- reports/VISION_TO_EXECUTION_MAP_2026_07_03.md: видение владельца (все стратегии идеально + ИИ на пульсе + side-split + наклонные/горизонтальные уровни + перенос на FX-боковики) замаплено на модули и фазы. Почти под каждый пункт модуль ЕСТЬ; разрыв не в стройке, а в wiring+доказательстве. Стандарт «идеально» зафиксирован: тесты/причинность -> флаги/атрибуция/breaker -> OOS+cross-symbol+side-split -> данные через coverage+cost гейты. ИИ-подстройка ТОЛЬКО в рельсах. «Идеальная стратегия без эджа = идеальный слив».

## ДОБАВЛЕНО 2026-07-03 (архитектура: самоусовершенствование + защита от регрессии, Claude)
- reports/SELF_IMPROVEMENT_AND_REGRESSION_DEFENSE_2026_07_03.md: (I) 5 слоёв обороны от регрессии (код/данные/стратегия/портфель/процесс — регрессия должна пробить все пять до денег); (II) маховик самоусовершенствования decision_bus -> ИИ-майнер -> A/B на OOS -> Proposal в TG -> аппрув -> флаг -> замер -> обратно (технологии из ящика вписываются ПО ЗАСЛУГАМ, не разом); (III) 3 яруса ИИ по скорости (бар=код-рельсы без LLM; час=алерты+ИИ-разбор; неделя=LLM-синтез+Proposal). Граница: ИИ не крутит параметры live напрямую, только риск/режим/жизн.цикл в рельсах + предложения через гейты.
- Порядок включения маховика: ATT1 wiring (уже у Codex) -> рукав 2 + exposure_gate -> orchestrator scheduled -> ИИ-майнер после 4-6 недель bus-данных. Сейчас маховик крутится вручную (чат Claude = узлы 2-4), wiring автоматизирует.

## ДОБАВЛЕНО 2026-07-03 (WIRING ATT1 РЕАЛИЗОВАН — decision_bus+edge_monitor в коде, Claude)
- bot/att1_live_wiring.py (6 тестов) + 10 точечных врезок в smart_pump_reversal_bot.py (import, minqty-флаг, 5 skip-точек, enter c bus_id на tr, outcome на CLOSE от ФАКТИЧЕСКОГО риска qty*|entry-sl|, почасовой edge_check в heartbeat с TG-алертом на смену статуса). Всё за флагами default OFF: ATT1_DECISION_BUS_ENABLE, ATT1_EDGE_MONITOR_ENABLE. Каждая функция exception-proof (сбой wiring НИКОГДА не трогает ордер-путь). edge_monitor = ALERT-ONLY (breaker остаётся единственным автостопом). Baseline 0.054R (fee-stress 10/5bps).
- Тесты: 745 passed (вся сетка, включая импорт-тесты большого файла). Синтаксис проверен ast.
- Codex: деплой обычным путём (флаги НЕ ставить) -> сутки стабильности -> OK владельца -> добавить в env оба флага=1 -> проверить появление runtime/decision_bus.jsonl и runtime/att1_edge_health.json. Rollback = убрать флаги.
- Маховик самоусовершенствования: узел [1] (атрибуция) теперь В КОДЕ, не только в спеке.

## ДОБАВЛЕНО 2026-07-03 (план капитала $3000, Claude + владелец)
- reports/CAPITAL_ALLOCATION_PLAN_2026_07_03.md: Bybit $2000 (ATT1 + будущий рукав 2; больший депозит чистит minqty-fallback статистику), Alpaca $500 (стабилизатор, выходные), резерв $500 (мгновенный canary для PASS-гейта / FX live позже / буфер). Правила top-up ФОРМАЛЬНЫЕ: +$100-200/мес только в edge_monitor=healthy рукав с expectancy>0 на >=10 сделках; нет healthy — в резерв; НИКОГДА не докидывать в degraded/halt (мартингейл руками). Кварт. $500 — в новый прошедший гейт рукав. FX live только после OOS на 2.4г + >=4 нед. демо в плюс.
- Ожидания зафиксированы честно: сейчас ~$10-15/мес (фаза доказательства), после разгона ATT1 ~$525/год до рукава 2, цель портфеля 20-30%/год на растущей базе. Нормальные DD: $60-100 Bybit. Codex: подтвердить баланс Bybit + базовый % риска в конфиге.

## ДОБАВЛЕНО 2026-07-03 (Codex live recovery + текущие screening facts)
- Git: локальные коммиты до `2a99f00` запушены. `ceca153` ATT1 wiring задеплоен на сервер целевыми файлами (`smart_pump_reversal_bot.py`, `bot/att1_live_wiring.py`, `bot/decision_bus.py`, `bot/edge_monitor.py`). Первичный рестарт упал из-за недокопированного `bot.decision_bus`; после копирования зависимостей `py_compile` OK, `systemctl reset-failed && start` поднял `bybot.service`.
- Live после recovery: `bybot.service=active`, `dry_run=False`, `trade_on=True`, `open_trades=0`, `regime=bull_chop`, `equity≈120.20 USDT`, `ws_guard_active=0`, hard block/safe mode off. `ATT1_DECISION_BUS_ENABLE` и `ATT1_EDGE_MONITOR_ENABLE` НЕ заданы — wiring стоит, telemetry пока off по плану «сутки стабильности -> owner OK -> включить».
- Risk calibration: `.env RISK_PER_TRADE_PCT=1.0`, heartbeat `base_risk_per_trade_pct=1.0`, фактический `risk_per_trade_pct=0.44` из-за `orch_global_risk_mult=0.55` и `allocator_global_risk_mult=0.80`. ATT1 r001 canary `ATT1_RISK_MULT=0.10`, значит фактический номинальный риск ATT1 сейчас около `120.2 * 0.44% * 0.10 = $0.053`/сделка до minqty/fallback.
- Live ATT1 config: override `configs/att1_short_r001_canary_20260702.env`, short-only, `MAX_POSITIONS=3`, `ATT1_MAX_OPEN_TRADES=3`, allowlist BTC/ETH/SOL/ADA/LINK/LTC/DOT/SUI плюс runtime добавляет WLD/XLM/ZEC в текущем heartbeat. Непруфнутые risk_mult: flat/range/bounce/ivb1/midterm/breakdown = 0.0.
- Research status: локальные `screen` старые `fx_1h_major_relaxed_gate_20260703` и `crypto_structure_clean_gate_20260703` выглядят как зависшие/пустые оболочки; не считать их источником новых фактов без fresh files.
- Already-readable results: `fx_h1_clean_gate_20260703` (59d only) нашёл weak pulse `AUDUSD session_range_fade` до `32 trades, +6.20R, PF1.28`, но это НЕ live-grade из-за короткой истории. `xau_round_sweep_long_20260703` отрицателен (лучшее -2.83R PF0.89). `xau_structure_break_long_20260703` имеет тонкий XAU-short pulse (до +12.39R PF1.10), но XAU H1 coverage был дырявый (93.4%), значит только re-screen after backfill. Raw crypto BOS short на clean symbols сразу отрицателен (первые строки PF ~0.74-0.79), raw structure не кандидат.
- Новые jobs: `fx_h1_session_range_relaxed_20260703` запущен отдельно на long `data_cache/forex_1h`, setup=session_range_fade, majors, H1, `max_gap_bars=24`, XAU исключён до backfill. `fx_yf_1h_backfill_20260703` запущен в отдельный cache `data_cache/forex_yf_1h_20260703` (EUR/GBP/USDJPY/AUD/XAU, yfinance 730d 1h) как research-proxy, основной cache не перетирается.
- Следующий порядок: (1) утром/через несколько часов проверить `screen -ls`, логи `logs/manual_research/fx_h1_session_range_relaxed_20260703.log` и `fx_yf_1h_backfill_20260703.log`; (2) если yfinance-cache чистый, прогнать `run_fx_native_harness` по session_range_fade/round_sweep на этом cache; (3) не включать ARF2/structure/raw BOS в live без OOS-symbol strict gate; (4) после суток стабильности ATT1 wiring — только по owner OK включить decision_bus/edge_monitor флаги.

## ДОБАВЛЕНО 2026-07-04 night prep (Codex)
- Bybit Unified пополнен и подтверждён read-only API: `totalEquity≈1019.28 USDT`, `available≈1019.28`, open positions 0. Live: `bybot.service=active`, `dry_run=False`, `trade_on=True`, `regime=bull_chop`, `risk_per_trade_pct=0.44`, `ATT1_RISK_MULT=0.10`; фактический номинальный риск ATT1 около `$0.45`/сделка, max 3 позиции около `$1.35`.
- Live semantics clarified: текущий денежный рукав только `ATT1 r001` = short-only отбой/касание наклонной линии сопротивления, НЕ пробой. `flat/range/ivb1/midterm/bounce/breakdown` в коде видны, но `risk_mult=0.0` и деньгами не торгуют.
- Live status: ATT1 пока не торговал после пополнения; `att1_try=21`, `att1_no_signal=21`, основные причины `att1_ns_trendline=14`, `att1_ns_first_bar=7`. Блокеров нет — ждёт валидную наклонку.
- Research facts before night: FX `session_range_fade` на длинной H1/yfinance истории отрицателен по EUR/GBP/USDJPY в первых проходах (много сделок, PF < 1). Raw crypto BOS/CHoCH также отрицателен (PF ~0.7-0.85), не кандидат.
- Server night run: найден старый positive ARS1/range candidate `r170` (`77 trades`, `+12.57R`, `PF 1.733`, 2 red months) из `backtest_runs/autoresearch_20260702_065007_ars1_side_regime_repair_20260627/ranked_results.csv`. Запущена серверная revalidation `screen=ars1_r170_recheck_20260704`, command tag `ars1_r170_revalidate_20260704`, низкий priority `nice=19`. Это единственный серверный ночной research, чтобы не перегружать 1GB live VPS.

## ДОБАВЛЕНО 2026-07-03 (fx_harness ускорен ~200x + КРИТИЧНО про equity, Claude)
- bot/fx_harness.py: O(n^2) -> O(n). _PrefixView (нулевое копирование причинного среза) + префиксный ATR (реплика market_context.atr бит-в-бит, включая non-finite TR путь). Golden-тест эквивалентности: сделки идентичны старой версии на 3 сетапах + NaN-бары (3 теста). 17k H1 баров = 0.02s на цикл харнесса. FX-свипы на 2.4г истории больше не ползут. Тесты: 748 passed.
- КРИТИЧНО (из отчёта Codex): Bybit equity = $120.20, риск ATT1 = $0.053/сделку, номинал ~$2.65 < min-notional Bybit. При появлении сигнала вход, вероятно, зарежется по minqty (att1_skip_minqty/notional_small) — канарейка может «молчать» не из-за редкости сетапа, а из-за РАЗМЕРА. ДЕЙСТВИЕ ВЛАДЕЛЬЦА: довести Bybit до $2000 по CAPITAL_ALLOCATION_PLAN. Codex: следить за att1_skip_minqty в diag; после пополнения счётчик должен перестать расти.
- AUDUSD session_range_fade 59d: +6.20R PF1.28 32tr = пульс, ждём long-history вердикт (fx_yf_1h_session_range на новом чистом кэше). НЕ live-grade до OOS на 2.4г + cross-pair.

## ДОБАВЛЕНО 2026-07-04 morning (Codex — live + ARS1 decision)
- Live-сервер проверен после пополнения: `bybot.service=active`, `dry_run=false`, `trade_on=true`, `open_trades=0`, `regime=bull_chop`, `risk_per_trade_pct=0.44`, `operator_live_override=configs/att1_short_r001_canary_20260702.env`. Единственный денежный рукав остаётся `ATT1 r001 risk_mult=0.10`; `flat/range/ivb1/midterm/bounce/breakdown=0.0`. Блокеров нет: ATT1 молчит из-за отсутствия валидной наклонки (`att1_ns_trendline` доминирует), а не из-за freeze/safety.
- Server research: `ars1_r170_revalidate_20260704` завершён: `68 trades`, `+13.12R`, `PF 1.864`, `WR 29.4%`, `DD 3.34R`, 3 красных месяца из 10. Символы: DOT +7.49R, ADA +2.73R, LINK +2.04R, SUI +1.21R, LTC -0.35R. Стороны почти симметричны: long +6.62R, short +6.50R.
- Локальная ARS1 r170 диагностика:
  - no-LTC (`ADA/LINK/DOT/SUI`): `70 trades`, `+12.91R`, `PF 1.825`, `DD 3.66R`, 2 красных месяца из 10; long +6.56R, short +6.35R.
  - long-only: `47 trades`, `+5.60R`, `PF 1.501`, `DD 7.28R`, 6 красных месяцев — слабее, не live.
  - short-only: `39 trades`, `+4.63R`, `PF 1.557`, `DD 2.42R`, 4 красных месяца — аккуратный диверсификатор, но маловат.
  - no-LTC rolling 4x90d: `+3.47R / -0.12R / +3.60R / +5.78R`, 3/4 положительных, total `+12.73R`, median `+3.54R`, min fold trades 14. `oos_selector` => `passes=True`, reason `robust_plateau`.
- Additivity sanity:
  - ATT1 r001 solo: `290 trades`, `+27.77R`, `PF 1.402`, `DD 6.55R`, 2 красных месяца.
  - ATT1 r001 + ARS1 no-LTC fixed: `407 trades`, `+33.35R`, `PF 1.397`, `DD 7.16R`, 2 красных месяца; вклад ARS1 `+12.44R/61tr`, ATT1 `+20.91R/346tr`.
  - Вывод: ARS1 no-LTC — первый реальный кандидат на второй крипто-рукав, но не включать вслепую. Он добавляет доход/частоту, но слегка ухудшает DD относительно ATT1 solo. Следующий безопасный шаг: `shadow`/paper telemetry или tiny canary `range risk_mult <=0.03-0.05` с отдельным breaker+expiry и запретом LTC; не добавлять как равный risk=0.10.
- ARF2 failed-breakout: focused-подбор был плюсовой (`+21.94R PF1.52`), но OOS-symbol gate на 15 новых символах провалился (`-15.48R PF0.83`). ARF2 НЕ кандидат в live; проблема = symbol pocket/overfit.
- FX/CFD: `session_range_fade` на длинной H1 истории EUR/GBP/USDJPY отрицателен; XAU round/structure текущие вердикты небоевые из-за coverage и отрицательных результатов. FX-трек остаётся research, не live.
- Текущий локальный процесс: старый `screen fx_1h_major_relaxed_gate_20260703` всё ещё считает и ест CPU; его результаты считать diagnostic-only до завершения. Новые полезные ночные задачи: ARS1 no-LTC additivity/telemetry packaging и/или ARS1 shadow config, а не ещё один raw BOS/FX range sweep.
- Подготовлен config-proposal: `configs/ars1_r170_noltc_tiny_canary_20260704.env` (`ENABLE_RANGE_TRADING=1`, `RANGE_RISK_MULT=0.03`, no-LTC, r170 params). Это НЕ задеплоено и НЕ live; применять только после явного owner OK.

## ДОБАВЛЕНО 2026-07-04 continuation (Codex — ARS1 OOS-symbol gate)
- Claude generic range breaker commit уже в HEAD: `193a624 feat: generic sleeve breaker+expiry...`. Range-канарейка теперь имела бы breaker/expiry, но это не снимает requirement на OOS-symbol PASS.
- ARS1 fixed r170/no-LTC OOS-symbol gate выполнен по заранее отделённой корзине `BTC/ETH/SOL/DOGE/ATOM/AVAX/1000PEPE/HYPE/TAO/ONDO`. Результат: `293 trades`, `-16.90R`, `PF 0.743`, `DD 22.17R`, 7 красных месяцев из 11, positive symbols `2/10` (`ONDO +4.02R`, `ATOM +2.34R`). Preregistered criterion (`>=50% symbols+`, total PF>1.1) => FAIL.
- Расширенная ARS1 symbol-matrix по cached OOS symbols (исключены `ADA/LINK/DOT/SUI/LTC`) также FAIL: 14 ok symbols, positive `4/14`, crude symbol PF `0.691`, total `-5.99R`. Top positives: `ONDO +4.96R`, `TAO +4.08R`, `ATOM +3.27R`, `ETH +1.07R`. Laggards: `HYPE -5.63R`, `SOL -3.50R`, `1000PEPE -2.53R`.
- Post-hoc top3 pocket `ONDO/TAO/ETH`: 360d `53 trades`, `+11.82R`, `PF 2.073`, `DD 2.75R`, but 4x90d folds `+3.11/-0.12/-0.17/+7.45R`, only `2/4` positive, `oos_selector` FAIL reason `unstable_frac_pos_0.50`. Не live.
- Decision: ARS1/range НЕ включать в live сейчас. Проблема не в breaker, а в переносимости по символам. Следующий research only: build/use dynamic symbol-picker for range suitability, then run symbol×time OOS again. `configs/ars1_r170_noltc_tiny_canary_20260704.env` помечен BLOCKED/RESEARCH ONLY.
- Добавлен tooling: `scripts/run_ars1_symbol_matrix.py` — fixed-param ARS1 per-symbol matrix для воспроизводимых symbol-transfer проверок.

## ДОБАВЛЕНО 2026-07-04 (ревью ARS1 canary + generic sleeve breaker, Claude)
- РЕВЬЮ ARS1 no-LTC кандидата: цифры хорошие (70tr +12.91R PF1.83, rolling 3/4+, oos_selector pass), НО две дисциплинарные дыры ПЕРЕД canary:
  (1) СИМВОЛЫ ВЫБРАНЫ ПОСЛЕ АНАЛИЗА: allowlist ADA/LINK/DOT/SUI из свипа + LTC исключён post-hoc как «слабейший» — это ровно паттерн ARF2 (focused +25.87R -> OOS-символы -15.48R). ARS1 ОБЯЗАН пройти OOS-symbol gate на свежем наборе (DOGE/XRP/AVAX/ATOM/BNB/XLM/TAO/SOL/BTC/ETH, 15m из 5m кэша, params r170 БЕЗ изменений, пре-регистрация: >=50% символов+, суммарный PF>1.1) ДО включения деньгами. Плюс раскрыть цифру С LTC (честный full-set результат).
  (2) У range-рукава НЕ БЫЛО breaker/expiry (ATT1-защита на него не распространялась) — ЗАКРЫТО кодом.
- КОД: _sleeve_breaker_state_env(prefix, strategy) — generic breaker+expiry для ЛЮБОГО рукава (ATT1 = wrapper, поведение бит-в-бит). Range-нога: breaker-блок перед sizing, soft-mult в effective_range_risk_mult (оба call-sites, включая minqty fallback), fail-safe блок при ошибке. Конфиг canary дополнен RANGE_BREAKER_*+expiry 2026-07-25 (hard -2.0 туже ATT1: рукав менее доказан). Тесты: 4 новых, 752 passed.
- ВЕРДИКТ Claude: canary НЕ включать до PASS OOS-symbol gate (день работы). Если PASS -> включать с моим конфиг-дополнением. Если FAIL -> в research, повторяем судьбу ARF2 БЕЗ потери денег. Дисциплина не торгуется: одинаковая планка для всех кандидатов.

## ДОБАВЛЕНО 2026-07-04 morning continuation (Codex — funded live + dynamic range picker)
- Bybit equity подтверждён штатным readonly-скриптом `scripts/exchange_account_status.py`: Bybit `equity_usdt=1019.3818`, `available_usdt=1019.3818`. Старый `operator_snapshot` всё ещё может показывать `ALLOCATOR_EQUITY_USD=123.04` из `.env`; это stale reporting artifact, не источник live sizing. Sizing в боте берёт `_get_effective_equity()` через Bybit `totalEquity`.
- Live сейчас: `bybot.service=active`, `dry_run=false`, `trade_on=true`, `open_trades=0`, `regime=bull_chop`, `risk_per_trade_pct=0.44`, `ATT1 r001 risk_mult=0.10`. Номинальный риск ATT1 около `1019.38 * 0.44% * 0.10 = $0.45` на сделку, max 3 позиции около `$1.35` риска.
- Сделок нет не из-за баланса/блокера: основная причина ATT1 — нет валидной short-наклонки (`att1_ns_trendline` доминирует). `flat_signal=1` был, но `flat/range risk_mult=0.0`, поэтому деньгами не торговал.
- Добавлен runner `scripts/run_ars1_dynamic_range_picker.py`: causal validation для гипотезы “ARS1 можно оживить не fixed allowlist, а динамическим range_scanner-подбором”. На каждом OOS-фолде: скорит символы только на прошлом train-window -> выбирает top range symbols -> гоняет fixed ARS1 r170 на следующем OOS-window -> оценивает через `oos_selector`.
- Запущен локальный long run в `screen=ars1_dyn_range_20260704`: `216` picker-policy кандидатов (`train_days 30/60/120`, `lookback 60/120`, `top_n 3/5/8`, `min_score .40/.50/.60`, width 1.5/2.0 x 8/12). Output: `reports/research/ars1_dynamic_range_picker_full_20260704/`, log: `logs/ars1_dynamic_range_picker_full_20260704.log`.
- Ранние результаты `17/216`: пока `0 PASS`; частые причины `thin_fold_0`, `insufficient_trades`, `frac_positive=0.25`. Это НЕ финальный вердикт, но пока dynamic-picker не выглядит как быстрый rescue range/пилы. Дождаться полного прогона перед решением.

## ДОБАВЛЕНО 2026-07-04 afternoon (Codex — portfolio expansion gates)
- ARS1 dynamic range-picker завершён: `216/216` picker-policy кандидатов, `0 PASS`. Best `td30_lb120_top3_s0.6_w1.5-8`: 4 folds, positive `2/4`, median `-0.54`, min fold `-2.78`, total trades `59`, reason `unstable_frac_pos_0.50`. Вывод: динамический `range_scanner` НЕ спас fixed ARS1 r170. Плюс сидит в отдельных fold/symbol pockets (`XRP/1000PEPE/LINK` last fold), не в устойчивом рукаве. `ARS1/range` остаётся `risk_mult=0.0`, live НЕ включать.
- ATT1 r001 long-only sanity на тех же 8 symbols/360d: `314 trades`, `net +0.47`, `PF 1.060`, `DD 1.046`. Символы около нуля (`SOL +0.22`, `BTC +0.16`, `DOT -0.12`). Вывод: long-side не готов; не добавлять “для активности”.
- Live check после пополнения: `dry_run=false`, `trade_on=true`, `open_trades=0`, `bull_chop`, `ATT1 risk_mult=0.10`. Причина отсутствия сделок та же: `att1_ns_trendline` (`141`) — нет валидной short-наклонки. `flat_signal=1`, но `flat/range risk_mult=0.0`, поэтому денег не касался.
- ARF2 failed_breakout повторно НЕ запускать как приоритет: focused DOGE/XRP/ONDO плюс был selection-pocket; OOS-symbol уже показал `-15.48R`, `PF0.83`. Следующее crypto-directional направление должно быть либо H4 real-data cascade, либо новая независимая механика, не ещё один post-hoc symbol pocket.
- Запущен локальный FX/CFD H1 trend пакет: `screen=fx_h1_trend_breakout_20260704`, log `logs/fx_h1_trend_breakout_20260704.log`, output `reports/research/fx_h1_trend_breakout_20260704/`. Setups: `session_breakout_retest,trend_pullback,round_level_sweep`, pairs `EURUSD,GBPUSD,USDJPY,XAUUSD`, H1 data with coverage/cost gates. Первый coverage EURUSD OK (`0.995732`). Это research-only, не live.
- Carry/funding scanner на сервере живой и видит spreads, но live-блокер для market-neutral carry — недостаточные балансы на второй ноге (Binance/Bitget) и delta-neutral executor validation. Это отдельный трек, не второй directional crypto sleeve.

## ДОБАВЛЕНО 2026-07-04 (ARS1 FAIL = победа процесса #3 + распечатываем козырь #1, Claude)
- ARS1 через dynamic range-picker: 216/216 кандидатов 0 PASS (лучший 2/4 фолда, медиана минус). Вчерашний PF 1.83 на выбранных символах был бы вторым ARF2 — гейт, который я потребовал перед canary, отработал. Деньги не тронуты. Это ТРЕТИЙ пойманный карман за 2 суток (ARF2, XAU round_sweep tiny-N, ARS1).
- СТРАТЕГИЧЕСКИЙ ВЫВОД: 5 мёртвых детекторов подряд на 1h крипто price-action = поляна перекопана всеми ботами мира. Смещаем поиск туда, где у нас МОНОПОЛИЯ: реальный liq-поток коллектора (месяцы на сервере), до сих пор НЕ тестированный (proxy-провал PF 0.26 не считается — данные были суррогатные).
- scripts/run_cascade_real_gate.py (4 теста, 756 passed): гейт cascade_reversal на РЕАЛЬНЫХ данных. Liq JSONL -> 5m бакеты; funding/OI c Bybit REST (пагинация) или CSV; coverage gate; пре-регистрированный мини-грид 16 комбо (fz 1.5/2.0, oi-drop 3/5, liq-pctile 90/95, rr 1.5/2.0), side-split, 4 фолда, консервативный SL-first + fees. Codex: гнать на сервере, где лежит runtime/liquidations/*.jsonl (окно = сколько собрано). НЕ расширять грид под результат.
- Ожидание ЧЕСТНО: каскады редки, окно недели -> N может не хватить даже на скрининг; тогда вывод = «копить поток дальше», не «мертво». FX H1 trend/breakout бежит параллельно.

## ДОБАВЛЕНО 2026-07-04 (план расширения = частота x положительное ожидание, Claude)
- Тезис владельца принят с уточнением: частота УМНОЖАЕТ знак ожидания (EURUSD: 1111 сделок x минус = -3061R). Расширение = только частота с плюсом.
- ПРЕ-РЕГИСТРАЦИЯ reports/ATT1_UNIVERSE_EXPANSION_PREREG_2026_07_04.md: r001 short БЕЗ подкруток на 11 новых монетах (DOGE,XRP,AVAX,ATOM,BNB,BCH,XLM,1000PEPE,HYPE,TAO,ONDO; базовые 8 в прогон не входят — in-sample). Пороги PASS зафиксированы (группа PF>=1.15, 3/4 фолда, 60% символов+, fee-stress, >=40 сделок/360d). PASS -> все монеты в allowlist (риск 0.10 прежний, частота x3-4). FAIL -> тень на сам ATT1: пометить «узкий эдж», cap разгона 0.5. Частичного PASS нет, отбор монет по результату запрещён (черри-пик).
- ОЧЕРЕДЬ ЧАСТОТЫ (по стоимости): 1) ATT1 universe (прогон - часы, стратегия уже доказана); 2) cascade real-data gate (раннер готов, ждёт сервер); 3) FX H1 trend/breakout (бежит); 4) H4-структура/liquidity_sweep на реальном потоке (после каскадов, тот же датасет); 5) FX smart_grid на мажорах (после первого FX-рукава). Портфельная арифметика: 3 рукава по 2-4 сделки/нед = торговля почти каждый день БЕЗ единого частого рукава.

## ДОБАВЛЕНО 2026-07-04 (коллектор плотностей стакана — старт датасета, Claude)
- scripts/collect_bybit_orderbook_density.py (5 тестов, 761 passed): WS-коллектор Bybit orderbook.50 по образцу liq-коллектора. Держит книгу (snapshot/delta, size=0 удаляет уровень), раз в 30с пишет ПЛОТНОСТИ (стенки >= 4x медианы уровня, в пределах 3% от мида, top-5/сторона, >= $10k) в runtime/orderbook/bybit_densities.jsonl. Компактно: ~3k строк/день на 10 символов. Чистые функции book/extract под тестами.
- ЗАЧЕМ: плотности/охота за ликвидностью из видения владельца требуют данных стакана, которых у нас НЕТ вообще. Каждый день без коллектора = минус день будущей истории. Детектор/стратегия — ПОЗЖЕ, когда накопится 2-4 недели данных, выровненных с нашим liq/OI/funding потоком (уникальный совместный датасет).
- Codex: поставить на сервер рядом с liq-коллектором (systemd/screen, лёгкий: одна WS-подписка, запись раз в 30с). НЕ research-нагрузка, live не мешает.
- Очередь liquidity-семейства: (1) cascade real gate (раннер готов) -> (2) liquidity_sweep на том же liq-датасете -> (3) детектор плотностей после 2-4 недель orderbook-данных.

## ДОБАВЛЕНО 2026-07-04 (кандидат владельца SWG1: среднесрок с флипом и трейлингом, Claude)
- Идея владельца зафиксирована как кандидат SWG1 (swing-continuation): в bear-режиме шорт коррекций по тренду; на подтверждённом развороте (CHoCH) флип в лонг; продолжение с trailing_stop. КОМПОЗИТ ГОТОВЫХ деталей: midterm_short_v1/trend_pullback (вход) + structure_break.CHoCH (флип) + trailing_stop.simulate_trail (выход) + regime_hmm (сторона по режиму, НЕ по ощущению). Новых модулей не требует.
- Место в очереди: ПОСЛЕ текущих гейтов (ATT1-universe, cascade, FX) — очередь не прыгаем. Прогон: D-тренд + H4-сигнал на 360d+ крипты, side-split, те же ворота (preflight -> wf_folds -> oos_selector -> OOS-symbols). Замечание: midterm-семейство уже в ящике с risk=0.0 до coverage+OOS — SWG1 это его ремонт через флип+трейлинг, не новая стройка.
- Принцип подтверждён: направление рынка определяет regime_hmm по данным (сейчас bull_chop), не настроение владельца/Claude. Short-крен включится сам при подтверждённом bear.

## ДОБАВЛЕНО 2026-07-04 (видение владельца финализировано: ML на данных НАШЕГО бота, Claude)
- Конечная цель зафиксирована: полноценный электронный трейдер — изучает рынок, торгует портфель стратегий, постоянно подстраивается и самоулучшается; венец = ML, обученный на СОБСТВЕННЫХ данных бота (не на общих ценах — там нас переигрывают фонды; на наших уникальных датасетах конкурентов нет).
- ML-дорожка (Ф4+, каждая модель через те же гейты: флаг -> A/B на OOS -> включение по результату):
  1) МЕТА-ЛЕЙБЛИНГ (первый): классификатор «брать ли сигнал» на контексте decision_bus (режим/фильтры/риск -> исход). Поднимает WR существующих рукавов. Данные: сотни сделок с телеметрией -> копятся с включения флагов ATT1.
  2) Exit-качество по MFE/MAE (когда трейлить/фиксировать). 3) ML-ранжирование символов для сканеров. 4) Апгрейд regime-модели (HMM -> обучаемая).
- Инфраструктура-семя уже есть: trades.db.ml_samples + _db_log_ml_close пишут при закрытии; decision_bus (код готов); плотности/liq/OI/funding потоки. Каждый live-день = обучающие данные.
- Требование честно: ML без сотен размеченных сделок = оверфит-машина. Порядок нерушим: сначала рукава наторговывают датасет, потом ML их улучшает. Всё сегодняшнее (телеметрия, коллекторы, канарейки) = подготовка датасета для этого видения.

## ДОБАВЛЕНО 2026-07-04 PM (Codex — реальные серверные шаги + FX runner fix)
- Live server: массовый `git pull` НЕ делался, потому что `/root/by-bot` грязный и старее локального HEAD (`75de6bd` на сервере против локальных новых коммитов). Все изменения внесены точечно.
- ATT1 telemetry включена в live r001 config после проверки `open_trades=0`: `ATT1_DECISION_BUS_ENABLE=1`, `ATT1_EDGE_MONITOR_ENABLE=1`, `ATT1_EDGE_INTERVAL_SEC=900`, `DECISION_BUS_PATH=runtime/decision_bus.jsonl`, `ATT1_EDGE_HEALTH_PATH=runtime/att1_edge_health.json`, baseline `0.054R`. `bybot.service` перезапущен и активен; `dry_run=false`, `open_trades=0`, `regime=bull_chop`.
- При первом edge_check обнаружен ложный `halt`: монитор читал 7 старых ATT1-сделок из общей истории `trade_events`, а не только r001-canary после включения telemetry. Исправлено: `bot/att1_live_wiring.py` получил `ATT1_EDGE_START_TS`; на сервере выставлено `1783162792`. Новый health корректный: `status=watch`, `n=0`, `reason=insufficient_trades_0`. Локально и на сервере `tests/test_att1_live_wiring.py` => `7 passed`.
- Orderbook density collector реально поставлен и запущен на сервере: `screen=orderbook_density_20260704`, output `runtime/orderbook/bybit_densities.jsonl`. Подтверждено, что файл начал наполняться; первые стенки уже пишутся. Collector стоит рядом с `bybit_liquidations_collector_20260616`.
- Перед деплоем density collector пойман баг: `scripts/collect_bybit_orderbook_density.py --help` падал из-за `%` в argparse help. Исправлено (`%%`), добавлен regression test `test_parser_help_formats_percent_sign`. Локально и на сервере `tests/test_orderbook_density_collector.py` => `6 passed`.
- FX H1 runner: старый `fx_h1_trend_breakout_20260704` был остановлен как неэффективный — он 2+ часа крутил EURUSD trend/round setup и не доходил до useful result. Root cause: setup пересчитывал ATR по всему prefix на каждом баре.
- Исправление FX performance: `bot/fx_harness.py` теперь передаёт precomputed `atr_value` в setup, если setup явно поддерживает этот аргумент; `bot/fx_setups.py::round_level_sweep` принимает `atr_value` и передаёт его в `liquidity_sweep`. Это убрало O(n²) для round sweep без изменения торговой логики. Тесты `test_fx_harness.py`, `test_fx_harness_fast_equivalence.py`, `test_fx_setups.py`, `test_fx_cost_feasibility.py` => `20 passed`.
- Ускоренный FX H1 round sweep завершён: `reports/research/fx_h1_round_sweep_20260704_fast/`. EURUSD/GBPUSD positive rows = tiny-N (3-8 trades) и не являются edge. USDJPY H1 имеет weak research-pulse: до `30 trades`, `+5.98R`, `PF≈1.26`, `3/4 folds+`, но `preflight=False` из-за тонкого fold / недостаточной устойчивости. XAUUSD H1 заблокирован coverage gate (`coverage=0.9336`, `494 gaps`, `gap_over_35_bars`) — не тестировать до clean backfill.
- Новый handoff: `reports/CODEX_HANDOFF_2026_07_04_PM.md`. Новый prompt для переезда: `reports/NEW_CHAT_KICKOFF_PROMPT.md`.

## ДОБАВЛЕНО 2026-07-04 PM (телеметрия ВКЛЮЧЕНА + дорожная карта по времени, Claude)
- ВЕХА: ATT1 telemetry LIVE (bus+edge_monitor), ложный halt пойман и изолирован Codex'ом через ATT1_EDGE_START_TS (health теперь watch/n=0 — корректно). Density collector на сервере, 2205+ строк за первые часы. FX runner ускорен Codex'ом (round_level_sweep O(n²) убран). USDJPY H1 слабый пульс (~30tr +5.98R PF1.26, preflight не PASS) — глубже OOS. Маховик данных ЗАПУЩЕН: с 04.07 каждый день = обучающие данные.
- reports/ROADMAP_TIMELINE_2026_07_04.md: карта по времени. 48ч: каскады+юниверс+Alpaca. Неделя 1: вердикты, портфель ATT1(+11 монет?)+Alpaca+канарейка. Недели 2-3: разгон ATT1 (expiry-ревью 20.07), orchestrator в TG, ~1-2%/мес. Август: 3-4 рукава, ИИ-майнер (4-6 нед bus-данных), run-rate цель 20-30%/год. Сентябрь+: ML мета-лейблинг. Контур отказа: все FAIL -> ATT1+Alpaca держат базу, сроки едут, последовательность ворот — нет.

## ДОБАВЛЕНО 2026-07-05 (ночная очередь + ревью сильнейших FX/среднесрок, Claude)
- CODEX_OVERNIGHT_QUEUE_2026_07_05.md: последовательный каскад на ~12ч отсутствия владельца: A) каскады на реальном liq (jsonl -> Mac, не жечь VPS) B) юниверс ATT1 по prereg C) FX trend_pullback+session_breakout_retest на 2.4г (сильнейшее FX-семейство; USDJPY отдельно — пульс PF1.26) D) среднесрок short_v2 (WF) + v3 с ОБНОВЛЁННЫМ END=2026-07-04 (старые раннеры протухли: v3 март-2026, short_v2 дек-2024!) + side/per-period разрез E) XAU backfill -> ре-скрининг.
- Ревью: сильнейший среднесрок = short_v2 (bear D+H4, есть WF-раннер) и v3 (MACD-pullback BTC/ETH); их свежий прогон = база для SWG1 (флип+трейлинг поверх лучшего). Сильнейший FX = трендовое семейство (pullback/breakout-retest), фейды мертвы; USDJPY — единственный пульс.

## ДОБАВЛЕНО 2026-07-04/05 execution (Codex — фактический запуск очереди)
- Проверено: локальных research `screen`-процессов не было; на сервере live живой (`bybot.service active`), коллекторы живые (`bybit_liquidations_collector_20260616`, `orderbook_density_20260704`), ATT1 r001 без сделок (`edge_health watch/n=0`), blocker'ов нет. Значит очередь была правильной, но сама не крутилась.
- Cascade real-data gate запущен локально на серверном `runtime/liquidations/bybit_liquidations.jsonl` (73,681 событий, окно 2026-06-16 08:10 UTC .. 2026-07-04 13:40 UTC). Найден и исправлен баг в `scripts/run_cascade_real_gate.py`: loader выбирал самый большой cache-файл, а не файл/окно, пересекающееся с liq-window, поэтому свежие данные могли давать `too_few_bars_0`. Теперь loader мерджит все `SYMBOL_5_*.json`, фильтрует по requested window, dedupe по timestamp. Regression: `tests/test_run_cascade_real_gate.py` → `5 passed`.
- После refetch 20d 5m OHLC для 12 liq-symbols и фикса loader'а cascade gate стал валидным по данным: coverage `1.000` по всем 12 символам (`BTC,ETH,SOL,XRP,DOGE,ADA,NEAR,SUI,AVAX,BNB,LINK,LTC`), gaps=0. Результат: `0 trades`, `combos=0`, `reports/research/cascade_real_gate_20260705_fixed/`. Вердикт: текущий строгий cascade-trigger НЕ live-кандидат; это не data-fail. Следующее: копить liq-поток дольше и/или тестировать liquidity_sweep/другой cascade-trigger на том же датасете, без расширения гридов задним числом.
- ATT1 universe expansion оформлен как воспроизводимый runner: specs `configs/autoresearch/att1_short_r001_universe_expansion_20260705_base.json` (6/2 bps) и `..._stress.json` (10/5 bps), runner `scripts/run_att1_universe_expansion_20260705.sh`. Параметры r001 зафиксированы, symbols строго из prereg (`DOGE,XRP,AVAX,ATOM,BNB,BCH,XLM,1000PEPE,HYPE,TAO,ONDO`), базовые 8 excluded.
- ATT1 universe запущен локально в `screen=att1_universe_20260705`, log `logs/att1_universe_expansion_20260705/run_20260704_141740.log`. Первый шаг — prefetch 370d 5m до `2026-07-04`, затем base/stress autoresearch. Если Mac уснёт, screen остановится; если не уснёт — вердикт через часы.

## ДОБАВЛЕНО 2026-07-04/05 continuation (Codex — ATT1 universe result + 12h queue)
- ATT1 r001 universe expansion завершён. Base 6/2: `353 trades`, `net +7.93`, `PF 1.081`, `WR 53.8%`, `DD 9.16`, `neg_months=3` => FAIL prereg (`PF < 1.15`). Stress 10/5: `364 trades`, `net -9.24`, `PF 0.913`, `WR 52.5%`, `DD 13.53`, `neg_months=6` => FAIL (`PF < 1.05`, `net < 0`). Отчёт: `reports/ATT1_UNIVERSE_EXPANSION_VERDICT_2026_07_04.md`.
- Решение: НЕ расширять `ATT1_SYMBOL_ALLOWLIST` на все 11 новых символов. Частичный отбор DOGE/1000PEPE/ONDO запрещён prereg как cherry-pick; возможен только новый заранее зарегистрированный symbol-selection эксперимент. ATT1 остаётся живым доказанным, но более узким рукавом.
- FX H1 trend family запущен после ATT1: `screen=fx_after_att1_20260705`, output `reports/research/fx_h1_trend_after_att1_20260705/`, log `logs/fx_h1_trend_after_att1_20260705/run_20260704_142154.log`. На старте EURUSD coverage OK; trend_pullback на EURUSD даёт 0 сделок, часть configs отсекает cost gate. Research-only.
- Добавлен sequential watcher `scripts/run_after_fx_midterm_20260705.sh`: ждёт `fx_after_att1_20260705`, затем запускает `midterm_short_v2` refreshed window (`END=2026-07-04`, `DAYS=1095`, WF 360/45/15) и `midterm_v3` refreshed window (`END=2026-07-04`, `DAYS=1095`, tests 1-2 only). Запущен `screen=midterm_after_fx_20260705`.
