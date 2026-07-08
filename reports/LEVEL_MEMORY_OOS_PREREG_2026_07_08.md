# PRE-REG: Level-Memory sweep/reclaim — строгий OOS (2026-07-08)

Статус: exploration ПУЛЬС получен, promotion НЕ пройдена. Это пре-регистрация строгого
пути. Пороги и параметры замораживаются ДО прогона; не крутить под результат; всё в ledger.

## Что показал exploration (screen crypto_lm_sweep_reclaim_20260707b, 19 символов, 18 комбо)
- combo4: respect_min=0.65, rr=1.2, lookback=48 -> 83 сделки, +11.81R, PF 1.30, WR 56.6%, folds+ 2, PASS.
- combo5: respect_min=0.65, rr=1.6 -> +10.84R, PF 1.23, WR 48.2%, folds+ 2, PASS.
- respect_min=0.55 (все rr) — минус (PF 0.77-0.98). rr=2.0 — минус.
=> Живой карман УЗКИЙ: respect_min=0.65, rr {1.2, 1.6}. Узость -> обязателен OOS + per-period.

## ЗАМОРОЖЕННЫЕ параметры (без вариаций на строгом пути)
- respect_min = 0.65 (единственное значение)
- rr in {1.2, 1.6} (2 значения — это ВСЯ сетка, больше не добавлять)
- lookback = 48
- side: как в exploration (без изменения)
- издержки: fee 6bps taker + slippage 2bps (fee-stress вариант: 10/5 отдельной колонкой)

## Строгий путь (в порядке; STOP при первом FAIL)
1. **Broad preflight** на всех 19 символах: coverage-gate 5m (closure=None), min_trades>=40 на комбо,
   концентрация топ-символа < 0.35. Если концентрация >= 0.35 -> карман держится на 1-2 монетах -> FAIL.
2. **wf_folds** (purged/embargo, time-based): >= 4 фолда; PASS = 3/4 фолда net_R>0 И суммарный PF>=1.20.
3. **oos_selector** 40/8/robustness>0 (как ARF2): отобрать по in-sample, подтвердить на out-of-sample окне.
4. **OOS-символьный холдаут** (символы, которых НЕ было в свипе; сначала coverage>=0.99 5m):
   NEARUSDT, INJUSDT, TIAUSDT, SEIUSDT, ARBUSDT, OPUSDT, APTUSDT, RUNEUSDT.
   PASS = на холдауте PF>=1.15 И net_R>0 (при тех же замороженных параметрах).
5. **per-period** (обязательно): bull-нога / bear-нога / чоп раздельно. Если эдж только в одном режиме ->
   пускать ТОЛЬКО с regime-гейтом (не соло). Красные месяцы показать явно.

## Критерий PROMOTION -> shadow (risk=0)
Все 5 шагов PASS. Тогда: подключить как sleeve `lm_sweep_reclaim_v1` в shadow (risk_mult=0),
decision_bus enter/skip/outcome, свой подюниверс (ликвидные альты с coverage>=0.99), breaker
+ portfolio_health (уже готов). Канарейка (risk 0.05) — только после N>=20 shadow-сделок с
live-vs-backtest parity и OK владельца. Expiry-ревью 21 день.

## Anti-overfit чек-лист (в отчёт)
- концентрация топ-символа, топ-2, топ-3;
- доля PnL от 3 крупнейших сделок (если >50% — карман хрупкий);
- fee-stress 10/5 колонкой; MFE-capture; worst losing streak; max DD в R.
