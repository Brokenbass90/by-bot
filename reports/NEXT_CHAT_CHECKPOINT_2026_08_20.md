# Следующий чат: точка продолжения 20 августа 2026

Главный источник текущей правды: `docs/PRAVDA.md`.

## Не повторять уже сделанное

- Не подавать `BREAKOUT_*` в frozen Inplay: историческая частота уже воспроизводится.
- Не включать ATT1 stop ×3.30/×6 в shadow/live до adapter parity.
- Не переписывать limit fill как «касание = исполнение»: текущая paper-модель требует поглощения видимой очереди публичными prints.
- Не трогать live-риск, orders, decision bus или monolith по research-результатам.

## Проверить первым

1. `screen -ls`: `research_inplay_prospective`, `research_att1_limit_paper`, `research_bybit_wide_m5_20260820`.
2. Freshness:
   - `runtime/inplay_prospective_shadow_v1/historical_frequency_startup_gate.json`;
   - `runtime/att1_limit_execution_paper/status.json`;
   - `logs/bybit_wide_m5_preholdout_20260820.log`.
3. Direct broker truth before any live statement.
4. Scoped Git status; do not capture the remaining dirty worktree.

## Следующая разработка

1. ATT1/SBR1 research-vs-live adapter parity harness.
2. Alpaca exact live-contract replay plus GTC deployment audit.
3. XAU session/retest prereg and causal replay.
4. Worktree reference-map and thematic salvage.
5. Full SPA integration of the position console after the read-only phase proves stable.

## Безопасность

No order/cancel/close/risk change was authorized by this session. MT5 signal-copy remains disabled until a local secret, exact demo allowlist and explicit owner approval are present.
