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
