# Next chat checkpoint — 2026-08-11 13:16 UTC

## Начать отсюда

1. Прочитать `reports/CURRENT_HANDOFF.md` и
   `reports/CODEX_RECOVERY_SESSION_2026_08_11.md`.
2. Перепроверить direct broker/service/heartbeat/deploy receipt: operational
   evidence ниже временно и не заменяет свежий read.
3. Проверить scoped Git status; worktree принадлежит нескольким параллельным
   авторам. Не чистить, не архивировать и не делать общий commit.

## Последняя подтвержденная live истина

- Bybit direct broker flat: `open_position_count=0`.
- bybot active, PID `2334168`, fresh heartbeat, `open_trades=0`.
- atomic release `475745108b5e7ff0668011694646181ba6d9bd00`, receipt
  `/root/by-bot/runtime/deploy_receipts/atomic_live_475745108b5e_20260811T124041Z.json`.
- ATT1 short-only `risk_mult=0.10`; other sleeves zero/no-money.
- WS guard inactive at `13:16 UTC`, heartbeat age `0.4s`. No live
  restart/deploy required.

## Новые артефакты

- `research_lab/negative_trade_lab.py`;
- `reports/research/negative_trade_lab_20260811/`;
- `reports/research/negative_trade_lab_20260811/squeeze_long_discovery_base/forensics_5m_r/`;
- universe aliases in `strategies/inplay_retest_v3.py`;
- universe differentiation in `research_lab/experiment_preflight.py`;
- XSEC integrity changes in `scripts/xsec_shadow_cycle.py`;
- focused suite: `40 passed`.

## Следующие действия в порядке

1. Подтвердить, что `1bf5293` и `9702162` доступны в remote branch; не
   захватывать Claude artifacts в следующие scoped commits.
2. Не трогать reserved holdout.
3. Держать XSEC shadow; проверять только новые attributable markouts.
4. Когда освободится compute lane — preregistered retest3 wide reachability.
5. Затем public funding breadth и PIT-aware equities daily bundle.
6. Запустить squeeze phenotype ablations только по одному изменению.
7. Продолжать clean ATT1 N20 и exact execution/accounting parity.

## Запреты

- никакого авто-включения 85/141 модулей;
- никакого AI order/risk authority;
- никакого wide ATT1 live;
- никаких повышений ATT1 до прохождения clean N20 gate;
- никакого общего cleanup dirty worktree без owner/reference/reproduction audit.
