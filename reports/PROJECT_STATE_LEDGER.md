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
