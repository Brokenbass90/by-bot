# H4 каскады — спек РЕАЛЬНОГО теста (сбор данных + прогон) — для сервера/Codex

Proxy честно упал (596 сделок, PF 0.26, exp -0.62R). Это ПОДТВЕРЖДАЕТ: наивный фейд
спайка = минус. Настоящий H4-эдж (cascade_reversal) требует РЕАЛЬНЫХ триггеров, которых
локально нет. Ниже — что собрать и как прогнать. bot/cascade_reversal.py уже ждёт эти входы.

## Данные (research-host/сервер, где live-коллектор)
1. **Ликвидации**: `bybit_liquidations.jsonl` (коллектор уже пишет вперёд). Нужна история
   ≥60-90 дней по SOL/AVAX/LINK/MATIC (mid-caps; НЕ BTC/ETH — переполнено). Агрегировать в
   per-5m-bar liq_volume (USD).
2. **Open Interest**: OI time series 5m по тем же символам (Bybit API `/v5/market/open-interest`).
   ≥60-90 дней.
3. **Funding**: funding rate history 5m/8h по тем же (у нас есть data_cache/funding_rates — проверить
   покрытие mid-caps; добрать недостающее).
4. Свечи 5m по тем же (есть в кэше).

## Как прогнать (feed в cascade_reversal)
На каждом баре: cascade_reversal(price_rows, funding_window, oi_window, liq_window) ->
long_ok/short_ok. Вход = level_entry (SL 1 ATR / TP 2 ATR, как DeepSeek). Издержки: slippage_model
context="inplay" (каскады = высокий слиппедж, 5x). Фолды: wf_folds (purge+embargo). Отбор: oos_selector.

## Пре-регистрированные критерии PASS (H4)
- OOS: ≥3/4 фолда net>0, медиана>0, нет один-окно-героя, N≥40 (≥8/фолд), fee/slip-stress выживает;
- cross-symbol: работает на ≥2-3 из 4 mid-caps (не один символ);
- частота: заметно выше InPlay (каскады — частые внутридневные события; если реже — не наш кейс).
PASS -> shadow -> tiny canary $50 (breaker+expiry). FAIL -> H4 в архив гипотез, не форсим.

## Почему это приоритетнее расширения InPlay
InPlay = редкая level-нога (структурно мало сделок). H4 = событийная, потенциально ЧАСТАЯ ->
больше стат.мощности + это чистая механика (позиционный перегрев плеча, не прогноз). Если у
крипты вообще есть честный эдж на нашем капитале — вероятнее всего он здесь.

## Параллельно (не блокирует H4)
- Full-grid InPlay gate (идёт) -> вердикт по расширенному гриду.
- ARF2/ASB2/ACB1 wiring+gate (пила/отскоки) — когда освободится research-host.
- Alpaca $500 (владелец) — реальное семя, не ждёт ничего.
