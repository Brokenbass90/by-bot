# Codex queue — приоритеты (2026-06-29, вечер)

Owner: деплой+тесты на Codex, первые удачные входы сегодня/завтра, Alpaca завтра.
Не перегружать — список по приоритету, по одному.

## P0 — разморозка ATT1 canary (СЕГОДНЯ, owner дал OK)
- Operator override: `ALLOW_OPERATOR_LIVE_OVERRIDES=1`,
  `OPERATOR_LIVE_OVERRIDE_ENV=configs/att1_short_canary_20260629.env`, restart.
- Verify heartbeat: att1=0.10 short-only, flat/range/breakdown/asb1/elder=0.0,
  att1_breaker.enabled=true, ATT1_MAX_OPEN_TRADES=3, open_trades=0.
- Детали: `reports/ATT1_CANARY_ACTIVATION_2026_06_29.md`.

## P0 — Alpaca $500 live (ЗАВТРА к открытию рынка)
- Создать server-only `configs/alpaca_live_v38.env` (по `.env.example`), live-ключи.
- Dry-run `ALPACA_SEND_ORDERS=0` → проверить пики/стопы/cap≤$500 → после OWNER OK
  и открытия рынка `SEND_ORDERS=1`. v38: PF 6.47, 9/11 зелёных, maxDD -3.86%.

## P1 — добить research (идёт)
- ARF2 full sweep → выбрать строки с PF~1.5–2 + много сделок + ≤3 красных мес
  (НЕ PF-выбросы типа r055=5.25 — оверфит).
- post_arf2_queue: IRV3 baseline / IRV3+volume_exit / ASB2 240d / ACB1 240d → прислать summary.

## P1 — ATT1 stop-width sweep (ответ на вопрос owner про «стопы подальше»)
- Свип `ATT1_SL_ATR_MULT` (напр. 0.6 / 0.9 / 1.2 / 1.6) short-only 240d, next-open,
  6/2 bps. Цель: видеть кривую WR↑ vs avg-loss↑ — wider стопы это TRADEOFF, не free win.
  Брать ту ширину, что даёт лучший expectancy + monthly стабильность, не просто max WR.

## P2 — заморозка балласта по инвентарю
- По `reports/STRATEGY_INVENTORY_2026_06_29.csv`: FREEZE(44)+ARCHIVE(27) → risk=0 /
  убрать из дефолтной ротации. Файлы НЕ удалять (owner: архив, не корзина).

## P2 — funding/carry: НЕ live пока
- Концентрация 57% в ESPORTSUSDT = красный флаг. До live: delta-neutral
  (`bot/carry_neutral.py`) + hedge/balance validation. GWEI/SLX — норм кандидаты,
  только market-neutral, без концентрации.

## P3 — форекс/золото demo (параллельный стабильный рукав, БЕЗ денег)
- Получить OANDA demo key → `run_forex_demo_canary_cycle.sh` на демо (zero risk).
  Форекс/XAUUSD стабильнее крипты (24/5, глубина, тайт спреды), рукав уже построен.
  Это можно крутить параллельно — деньгами не рискуем.

## ОБНОВЛЕНИЕ 2026-06-30 (вечер) — приоритет: ВАЛИДАЦИЯ, не новый код
Накоплено много кода, 0 честных WF. Гнать WF, приоритет — механика (деньги не от предсказания):
1. **Mechanical (деньги):** прогнать `walkforward_pair_arb.py` / `validate_pair_arb.py` (cointegration) на ликвидных парах (ETH/BTC, SOL/ETH, ARB/OP...). Carry: re-gate на высоком funding + delta-neutral (`carry_neutral`). Basis arb — следом.
2. **Directional (правда):** честный WF ASB2/ACB1 (вкл. adaptive-вариант: ASB2_ADAPTIVE=1 / ACB1_ADAPTIVE=1) + ARF2 упрощённый (vol-filter уже ВКЛ) + InPlay V4.
3. **Commit:** весь набор Claude (adaptive_context, market_context апгрейды, render v2, ASB2/ACB1 adaptive, ARF2 fix, strategy_breaker/volume_exit/carry_neutral + тесты = 66 зелёных).
4. Alpaca dry-run к открытию рынка.
Вернуть: WF-цифры по pair-arb + carry в первую очередь.
