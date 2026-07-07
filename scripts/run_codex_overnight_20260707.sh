#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PY:-.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

RUN_ID="${RUN_ID:-codex_overnight_20260707}"
LOG_DIR="logs/${RUN_ID}"
REPORT_DIR="reports/research/${RUN_ID}"
mkdir -p "$LOG_DIR" "$REPORT_DIR"

echo "codex overnight start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')" | tee "$LOG_DIR/00_start.log"
cat > "$REPORT_DIR/MANIFEST.txt" <<EOF
run_id=${RUN_ID}
started_utc=$(date -u '+%Y-%m-%d %H:%M:%S UTC')
purpose=overnight search for next sleeves: crypto level/sweep, FX/CFD range/session, MRB repair, cascade data gate
live_money_impact=none; research-only, no orders
EOF

run_step() {
  local name="$1"
  shift
  local log="$LOG_DIR/${name}.log"
  (
    echo "=== ${name} start $(date -u '+%Y-%m-%d %H:%M:%S UTC') ==="
    echo "cmd=$*"
    "$@"
    local rc=$?
    echo "=== ${name} finish rc=${rc} $(date -u '+%Y-%m-%d %H:%M:%S UTC') ==="
  ) > "$log" 2>&1
}

run_step "01_fx_native_h1_range_sweep" \
  "$PY" scripts/run_fx_native_harness.py \
    --data-dir data_cache/forex_1h \
    --pairs EURUSD,GBPUSD,USDJPY,GBPJPY,AUDJPY,XAUUSD \
    --setups session_range_fade,round_level_sweep,session_breakout_retest,trend_pullback \
    --outdir "$REPORT_DIR/fx_native_h1_range_sweep" \
    --tp-rr 1.2,1.5,2.0,2.5 \
    --sl-atr 0.7,1.0,1.3 \
    --max-hold 48,120,240 \
    --fee-bps 1 \
    --slippage-bps 0.5 \
    --interval-min 60 \
    --coverage-interval-min 60 \
    --min-coverage 0.98 \
    --max-gap-bars 24 \
    --market-closure-gap-bars 72 \
    --max-fee-r 0.35

run_step "02_fx_m5_multi_strategy_gate" \
  "$PY" scripts/run_forex_multi_strategy_gate.py \
    --pairs EURUSD,GBPUSD,USDJPY,EURJPY,GBPJPY,AUDJPY,XAUUSD \
    --strategies failure_reclaim_session_v1,liquidity_sweep_bounce_session_v1,asia_range_reversion_session_v1,range_bounce_session_v1,breakout_continuation_session_v1,trend_retest_session_v2 \
    --data-dir data_cache/forex \
    --session-start-utc 6 \
    --session-end-utc 20 \
    --stress-spread-mult 1.5 \
    --stress-swap-mult 1.5 \
    --recent-days 28 \
    --min-base-net -999999 \
    --min-stress-net -999999 \
    --min-base-return-pct-est -999999 \
    --min-stress-return-pct-est -999999 \
    --min-stress-return-pct-est-month -999999 \
    --min-trades 12 \
    --max-stress-dd 600 \
    --min-recent-stress-net -999999 \
    --min-recent-trades 1 \
    --top-n 40 \
    --risk-pct 0.25 \
    --tag "${RUN_ID}_fx_m5_multi_strategy"

run_step "03_crypto_mrb_repair_z18" \
  "$PY" scripts/run_crypto_mrb_exploration_20260707.py \
    --days 360 \
    --symbol-limit 32 \
    --lookback 20 \
    --z-entry 1.8 \
    --sl-atr 1.5 \
    --tp-atr 2.0 \
    --max-hold-bars 36 \
    --rebalance-hours 4 \
    --min-trades 40 \
    --min-pf 1.0 \
    --min-positive-folds 2 \
    --tag "${RUN_ID}_mrb_z18"

run_step "04_crypto_mrb_repair_z24_fast" \
  "$PY" scripts/run_crypto_mrb_exploration_20260707.py \
    --days 360 \
    --symbol-limit 32 \
    --lookback 30 \
    --z-entry 2.4 \
    --sl-atr 1.2 \
    --tp-atr 1.4 \
    --max-hold-bars 24 \
    --rebalance-hours 4 \
    --min-trades 30 \
    --min-pf 1.0 \
    --min-positive-folds 2 \
    --tag "${RUN_ID}_mrb_z24_fast"

if compgen -G "runtime/liquidations/*.jsonl" > /dev/null; then
  LIQ_FILE="$(ls -1t runtime/liquidations/*.jsonl | head -1)"
  run_step "05_cascade_real_liq_gate" \
    "$PY" scripts/run_cascade_real_gate.py \
      --liq-jsonl "$LIQ_FILE" \
      --crypto-cache data_cache \
      --outdir "$REPORT_DIR/cascade_real_liq_gate"
else
  {
    echo "=== 05_cascade_real_liq_gate blocked $(date -u '+%Y-%m-%d %H:%M:%S UTC') ==="
    echo "blocked=no local runtime/liquidations/*.jsonl; pull server liquidation stream first"
  } > "$LOG_DIR/05_cascade_real_liq_gate.log"
fi

"$PY" - <<'PY' > "$LOG_DIR/99_collect_summary.log" 2>&1
from __future__ import annotations

import csv
import json
from pathlib import Path
from datetime import datetime, timezone

root = Path(".")
run_id = "codex_overnight_20260707"
log_dir = root / "logs" / run_id
report_dir = root / "reports" / "research" / run_id

lines = [
    "# Codex Overnight 2026-07-07",
    "",
    f"- generated_utc: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`",
    "- live_money_impact: `none; research-only`",
    "",
    "## Logs",
]
for p in sorted(log_dir.glob("*.log")):
    lines.append(f"- `{p}`")

lines += ["", "## Report Files"]
for p in sorted(report_dir.rglob("*")):
    if p.is_file():
        lines.append(f"- `{p}`")

def add_top_csv(path: Path, title: str, sort_fields: tuple[str, ...]) -> None:
    if not path.exists():
        return
    rows = []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception as exc:
        lines.extend(["", f"## {title}", f"- read_error: `{exc}`"])
        return
    def key(row):
        vals = []
        for field in sort_fields:
            try:
                vals.append(float(row.get(field, "nan")))
            except Exception:
                vals.append(float("-inf"))
        return tuple(vals)
    rows = sorted(rows, key=key, reverse=True)[:10]
    lines.extend(["", f"## {title}"])
    if not rows:
        lines.append("- no rows")
        return
    for r in rows:
        compact = {k: r.get(k) for k in r.keys() if k in {
            "pair", "setup", "variant", "name", "symbol", "side", "trades", "net_r", "pf",
            "stress_net", "stress_pf", "folds_pos", "pass", "pass_exploration", "score",
            "base_net", "base_pf", "recent_stress_net"
        }}
        lines.append(f"- `{json.dumps(compact, ensure_ascii=False)}`")

add_top_csv(report_dir / "fx_native_h1_range_sweep" / "summary.csv", "FX Native H1 Top Rows", ("net_r", "pf"))

for p in sorted((root / "reports" / "research").glob(f"*{run_id}_mrb*/*grid.csv")):
    add_top_csv(p, f"MRB Top Rows: {p.parent.name}", ("score", "net_r", "pf"))

summary = report_dir / "SUMMARY.md"
summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"saved={summary}")
PY

echo "codex overnight done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')" | tee "$LOG_DIR/DONE.log"
