# Control-Plane Audit 2026-04-23

Цель: перестать спорить на ощущениях и проверить, помогает ли стек `regime orchestrator + symbol router + portfolio allocator + health gate` каждой стратегии.

## Правило

Каждый кандидат теперь проверяется парно:

- `strategy-only`: стратегия сама по себе на тех же данных, комиссиях и slippage.
- `full-stack`: та же стратегия через полный control-plane.

Если full-stack оставляет меньше 55% сделок или меньше 45% net PnL от strategy-only, стек считается подозрительным для этого рукава и должен быть ослаблен/починен.

## Первые результаты

| Кандидат | Strategy-only | Full-stack | Диагноз |
|---|---:|---:|---|
| `impulse_ivb1` | +12.85 / 95 trades | +1.66 / 14 trades | frequency cut too hard |
| `breakdown_v1` | +21.73 / 126 trades | -5.80 / 141 trades | edge destroyed by stack |
| `support_bounce` before wiring fix | +19.22 / 129 trades | 0.00 / 0 trades | blocked by stack |
| `support_bounce` after wiring fix | +19.22 / 129 trades | +0.37 / 52 trades | stack needs relaxation |
| `flat_arf1` | +11.78 / 82 trades | +6.60 / 49 trades | stack preserved edge |
| `att1` | +38.01 / 402 trades | +28.24 / 369 trades | stack helped risk |
| `range_package` | +17.44 / 256 trades | -2.38 / 164 trades | edge destroyed by stack |
| `elder_v3` | +2.09 / 7 trades | 0.00 / 0 trades | blocked by stack |

## Findings

1. Технологии не надо выбрасывать целиком: для `att1` стек сохранил 92% сделок, 74% прибыли и снизил DD; для `flat_arf1` стек тоже сохранил edge.
2. Технологии нельзя больше считать автоматически полезными: `impulse`, `breakdown`, `range_package`, `support_bounce`, `elder_v3` показывают, что часть рукавов режется или портится.
3. Найден конкретный wiring bug: `support_bounce` должен получать символы через `BOUNCE1_SYMBOL_ALLOWLIST`, но registry писал профиль в `ASB1_SYMBOL_ALLOWLIST`. Из-за этого sleeve `bounce1` видел `symbol_count=0` и не включался.
4. `breakdown_v1` не просто режется, а портится: full-stack даёт больше сделок, но переводит итог в минус. Это признак неправильного режима/символов, а не только низкой частоты.
5. `impulse_ivb1` страдает от частоты: стек оставляет только 14 из 95 сделок. Здесь первый ремонт - не стратегия, а router/regime gate для impulse.

## Next Repairs

1. `support_bounce`: после wiring-fix прогнать router variants: broad fixed symbols vs historical scan vs anchor-only.
2. `impulse_ivb1`: проверить three-way replay: no router, router only, full-stack. Цель - найти слой, который съедает 80% сделок.
3. `breakdown_v1`: сравнить bear-only strategy-only vs full-stack bear windows. Если стратегия в тех же bear windows плюсует без router, чинить symbol router.
4. `range_package`: разложить пакет на `breakdown`, `flat`, `range` внутри full-stack и не включать `range` в live, пока он не перестанет уничтожать портфель.
5. `elder_v3`: policy сейчас держит `elder_ts_v3` на нулевых multipliers. Это честно блокирует live, но research replay должен иметь override-policy для проверки кандидатов.

## Decision

До ремонта full-stack не повышать риск для новых crypto рукавов. Безопасные кандидаты на canary остаются только те, где стек сохранил edge: в текущем срезе это `att1` и `flat_arf1`.
