# PUMP4 V1 — точная версия источника и расчёта корректной экономики (для Codex, 26.10.2026)
Ежедневный пересчёт `pump4_polnyy_povtor.py` (хук `ocenshchiki_ezhednevno`, раз в сутки после 06:00 UTC). V1 не меняется.
| что | значение |
|---|---|
| стратегия | `strategies/pump_fade_v4r.PumpFadeV4RStrategy` (sha256 cea7a2cc9151d22d…), env PUMP4_ALLOW_LONGS/SHORTS=1, allowlist = вселенная |
| вселенная | `data/pump4_v1_universe_20261020.json`, 137 монет (sha256 e7cca156e48dedd4…; копия конфига Codex) |
| свечи | Bybit v5 `/market/kline` category=linear interval=60; только закрытые (`open + 1 ч ≤ now`); прогрев 1 200 ч |
| подача | каждая закрытая свеча подряд, `rows = b[:i+1]`; сигнал на закрытии i, вход открытием i+1 (журнал тени не используется) |
| сделка | `pump4_pereschet.simulate`: стоп ×4, цели сигнала, доля TP1 0.55, удержание 168 ч, MAX_LEV 100; тейкер 6 bps/сторона |
| не учтено | фандинг, проскальзывание (задержка входа 5 мин ≈ −0.001R, замер 25.10) — за Codex |
| контроль | `sim_geo`, 10 случайных входов той же монеты, seed 20261020 (бенчмарк; пул баров не ограничен датой сигнала) |
| история / вперёд | сигналы с ts < 2026-10-26 09:00 UTC — история (повтор, 84 закрытых на 26.10); ts ≥ — проспективные |
| журнал вперёд | `data/pump4_vpered_zhurnal.jsonl`, только дописывание: SIGNAL (первое появление, задержка обнаружения), ISHOD (первое закрытие), REVIZIYA (исчез / сменил сторону / изменился R) с sha256 строки; тест `fabrika/test_pump4_zhurnal_vpered.py` |
| результат прогона | `results/pump4_polnyy_povtor_<время>.json`: `svod.vse` (всё с 01.09), `svod.tolko_vpered`, `svod.zhurnal_vpered`, `sdelki` |
Для parity: эталон 84 сигналов — `results/pump4_polnyy_povtor_20261026T0857Z.json` (`sdelki`, sym/ts/side). Старый `pump4_pereschet`
читает `data/ten_pump4.jsonl` (тень с пропусками свечей) → его цифры только описательные.
