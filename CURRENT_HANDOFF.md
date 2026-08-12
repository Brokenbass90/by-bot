# Current handoff — 2026-08-12 11:12 UTC

Это первая точка входа после паузы или перехода в новый чат. Подробности:
`reports/PROJECT_STATE_AND_RESEARCH_REPORT_20260812.md`, затем
`reports/CURRENT_PROJECT_ROADMAP.md`.

## Git truth

- branch: `codex/dynamic-symbol-filters`
- pushed remote SHA: `3201b7449bb05dbdda24ddbb1c195ef297306e54`
- последние commits:
  - `fb4500b` — MPL two-arm receipt, обе руки REJECT;
  - `7c03cc5` — causal Inplay + prospective zero-risk collector;
  - `3201b74` — worktree audit, data contracts, canonical report.
- сотни чужих/Claude dirty files сохранены и не входят в эти commits.

## Live truth

- server-side direct Bybit checker: `retCode=0`, open positions `0` на 11:03 UTC;
- local Bybit read-only key expired (`33004`), его вывод не использовать;
- live monolith, orders, risk и services в сессии не менялись;
- ATT1 остаётся tiny canary `0.10`; повышение только после clean N20 и parity.

## Research continuity

- local supervisor: `6/6 healthy`;
- Inplay screen: `research_inplay_prospective_20260812`;
- Inplay authority: public-only, authentication/order/risk/capital `false`;
- Alpaca PIT: на последнем срезе `816/1000`, failures `0`, GET-only;
- alt24 L2: `29,562` observations, 24 symbols, collecting;
- server L2: tape `1.31GB`, free `6.4GB`, guard `5GB`; guard не обходить.

## Ноги

- ATT1 majors: единственная crypto money-canary, wide universe отрицателен;
- Inplay ETH: `CAUSAL_VIABLE_SHADOW_ONLY`, N455, 3/4 positive folds;
- MPL: обе prereg hands REJECT, не спасать tuning;
- XSEC causal V1: REJECT, stress total `-5.82%`;
- funding dynamic/frozen: только forward shadow;
- Alpaca: SAFE_HOLD, annual conclusion только после PIT validator/replay.

## Блокеры и следующий порядок

1. В кабинетах перевыпустить Alpaca/Massive keys; обновить secrets, выполнить
   GET-only smoke, затем отозвать старые. Восстановить отдельный local Bybit
   read-only checker key.
2. Дождаться Alpaca `1000/1000`, запустить validator и exact live-contract
   annual base/stress replay.
3. Не менять Inplay: накопить prospective N30–50, затем regime/symbol OOS.
4. Собрать spot↔perp exact mapping и causal funding/carry replay.
5. Разбирать `176` dirty code candidates пакетами 5–10 через reproduction;
   ничего массово не удалять.

## Проверка после паузы

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
./CHECK_RESEARCH_STATION.command
screen -ls
python3 -m json.tool runtime/inplay_prospective_shadow_v1/status.json
python3 -m json.tool research_lab/data/alpaca_pit_daily_v1/status.json
```

Для direct broker truth использовать server checker read-only. Не делать
deploy/restart только на основании локальных status-файлов.
