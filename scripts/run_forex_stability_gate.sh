#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

PAIRS="${FX_PAIRS:-EURUSD,GBPUSD,EURJPY,USDJPY,AUDJPY,USDCAD,GBPJPY}"
STRATS="${FX_STRATEGIES:-trend_retest_session_v1:conservative,trend_retest_session_v1:active,trend_retest_session_v1:eurusd_canary,trend_retest_session_v1:winrate_plus,trend_retest_session_v1:gbpjpy_stability_a,trend_retest_session_v1:gbpjpy_stability_b,trend_retest_session_v1:quality_guard,range_bounce_session_v1:default,range_bounce_session_v1:loose,breakout_continuation_session_v1:default,breakout_continuation_session_v1:strict,breakout_continuation_session_v1:active,breakout_continuation_session_v1:quality_guard,grid_reversion_session_v1:default,grid_reversion_session_v1:strict,grid_reversion_session_v1:active,grid_reversion_session_v1:eurjpy_canary,grid_reversion_session_v1:safe_winrate,trend_pullback_rebound_v1:default,trend_pullback_rebound_v1:strict,trend_pullback_rebound_v1:quality_guard}"

# Stage gate settings (strict enough for sane candidates)
FAST_TAG="${FX_FAST_TAG:-fx_stab_fast}"
FULL_TAG="${FX_FULL_TAG:-fx_stab_full}"
FULL_MAX_BARS="${FX_FULL_MAX_BARS:-15000}"
FULL_MIN_TRADES="${FX_FULL_MIN_TRADES:-40}"
FULL_MAX_STRESS_DD="${FX_FULL_MAX_STRESS_DD:-350}"
FULL_MIN_STRESS_RETURN_PCT_EST="${FX_FULL_MIN_STRESS_RETURN_PCT_EST:-0}"
FULL_MIN_RECENT_STRESS_NET="${FX_FULL_MIN_RECENT_STRESS_NET:--150}"

# Stability filters
MIN_MONTH_BOTH_PCT="${FX_MIN_MONTH_BOTH_PCT:-55}"
MIN_ROLL_BOTH_PCT="${FX_MIN_ROLL_BOTH_PCT:-55}"
REQUIRE_POS_MONTHS_GE_NEG="${FX_REQUIRE_POS_MONTHS_GE_NEG:-1}"
MIN_MONTH_STRESS_TOTAL="${FX_MIN_MONTH_STRESS_TOTAL:-0}"
MIN_ROLL_STRESS_TOTAL="${FX_MIN_ROLL_STRESS_TOTAL:-0}"
ROLL_WINDOW_DAYS="${FX_ROLL_WINDOW_DAYS:-28}"
ROLL_STEP_DAYS="${FX_ROLL_STEP_DAYS:-7}"
STAB_MIN_TRADES="${FX_STAB_MIN_TRADES:-30}"
STAB_MAX_DD="${FX_STAB_MAX_DD:-350}"
STAB_MIN_NET="${FX_STAB_MIN_NET:-0}"
STAB_MIN_RET_PCT="${FX_STAB_MIN_RET_PCT:-0}"

SESSION_START_UTC="${FX_SESSION_START_UTC:-6}"
SESSION_END_UTC="${FX_SESSION_END_UTC:-20}"
STRESS_SPREAD_MULT="${FX_STRESS_SPREAD_MULT:-1.5}"
STRESS_SWAP_MULT="${FX_STRESS_SWAP_MULT:-1.5}"

OUT_PREFIX="${FX_STAB_OUT_PREFIX:-docs/forex_stability_latest}"
TS="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="backtest_runs/forex_stability_gate_${TS}"
mkdir -p "${RUN_DIR}"

echo "forex stability gate start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "pairs=${PAIRS}"
echo "strategies=${STRATS}"
echo "full_max_bars=${FULL_MAX_BARS} full_min_trades=${FULL_MIN_TRADES}"
echo "stability: month_both>=${MIN_MONTH_BOTH_PCT}% roll_both>=${MIN_ROLL_BOTH_PCT}% pos_months>=neg=${REQUIRE_POS_MONTHS_GE_NEG}"
echo "stability candidate prefilter: trades>=${STAB_MIN_TRADES} dd<=${STAB_MAX_DD} net>=${STAB_MIN_NET} ret>=${STAB_MIN_RET_PCT}"

FX_UPDATE_STATE_AFTER_GATE=0 \
FX_GATE_TAG="${FAST_TAG}" \
FX_PAIRS="${PAIRS}" \
FX_STRATEGIES="${STRATS}" \
FX_MAX_BARS="${FX_FAST_MAX_BARS:-4500}" \
FX_MIN_TRADES="${FX_FAST_MIN_TRADES:-15}" \
FX_TOP_N="${FX_FAST_TOP_N:-20}" \
FX_MIN_BASE_NET="${FX_FAST_MIN_BASE_NET:-0}" \
FX_MIN_STRESS_NET="${FX_FAST_MIN_STRESS_NET:-0}" \
FX_MIN_BASE_RETURN_PCT_EST="${FX_FAST_MIN_BASE_RETURN_PCT_EST:--999}" \
FX_MIN_STRESS_RETURN_PCT_EST="${FX_FAST_MIN_STRESS_RETURN_PCT_EST:--999}" \
FX_MIN_STRESS_RETURN_PCT_EST_MONTH="${FX_FAST_MIN_STRESS_RETURN_PCT_EST_MONTH:--999}" \
FX_MAX_STRESS_DD="${FX_FAST_MAX_STRESS_DD:-300}" \
FX_MIN_RECENT_STRESS_NET="${FX_FAST_MIN_RECENT_STRESS_NET:-0}" \
FX_MIN_RECENT_TRADES="${FX_FAST_MIN_RECENT_TRADES:-8}" \
bash scripts/run_forex_multi_strategy_gate.sh

fast_dir="$(ls -1dt backtest_runs/forex_multi_strategy_gate_${FAST_TAG}_* 2>/dev/null | head -n 1 || true)"
if [[ -z "${fast_dir}" || ! -f "${fast_dir}/selected_combos.csv" ]]; then
  echo "fast stage output not found"
  exit 1
fi

picked="$(python3 - <<'PY' "${fast_dir}/selected_combos.csv" "${FX_FULL_COMBO_LIMIT:-10}"
import csv,sys
path=sys.argv[1]
limit=max(1,int(sys.argv[2]))
pairs=[]; strats=[]
with open(path,newline='',encoding='utf-8') as f:
    for i,row in enumerate(csv.DictReader(f)):
        if i>=limit:
            break
        p=(row.get('pair') or '').strip().upper()
        s=(row.get('strategy') or '').strip()
        if p and p not in pairs: pairs.append(p)
        if s and s not in strats: strats.append(s)
print(",".join(pairs))
print(",".join(strats))
PY
)"
full_pairs="$(printf '%s\n' "${picked}" | sed -n '1p')"
full_strats="$(printf '%s\n' "${picked}" | sed -n '2p')"
if [[ -z "${full_pairs}" || -z "${full_strats}" ]]; then
  echo "no fast candidates found for full confirm"
  exit 1
fi

FX_UPDATE_STATE_AFTER_GATE=0 \
FX_GATE_TAG="${FULL_TAG}" \
FX_PAIRS="${full_pairs}" \
FX_STRATEGIES="${full_strats}" \
FX_MAX_BARS="${FULL_MAX_BARS}" \
FX_MIN_TRADES="${FULL_MIN_TRADES}" \
FX_TOP_N="${FX_FULL_TOP_N:-12}" \
FX_MIN_BASE_NET="${FX_FULL_MIN_BASE_NET:-0}" \
FX_MIN_STRESS_NET="${FX_FULL_MIN_STRESS_NET:-0}" \
FX_MIN_BASE_RETURN_PCT_EST="${FX_FULL_MIN_BASE_RETURN_PCT_EST:--999}" \
FX_MIN_STRESS_RETURN_PCT_EST="${FULL_MIN_STRESS_RETURN_PCT_EST}" \
FX_MIN_STRESS_RETURN_PCT_EST_MONTH="${FX_FULL_MIN_STRESS_RETURN_PCT_EST_MONTH:--999}" \
FX_MAX_STRESS_DD="${FULL_MAX_STRESS_DD}" \
FX_MIN_RECENT_STRESS_NET="${FULL_MIN_RECENT_STRESS_NET}" \
FX_MIN_RECENT_TRADES="${FX_FULL_MIN_RECENT_TRADES:-8}" \
bash scripts/run_forex_multi_strategy_gate.sh

full_dir="$(ls -1dt backtest_runs/forex_multi_strategy_gate_${FULL_TAG}_* 2>/dev/null | head -n 1 || true)"
if [[ -z "${full_dir}" || ! -f "${full_dir}/raw_runs.csv" ]]; then
  echo "full stage output not found"
  exit 1
fi

cp "${full_dir}/raw_runs.csv" "${RUN_DIR}/raw_runs.csv"
cp "${full_dir}/gated_summary.csv" "${RUN_DIR}/gated_summary.csv" 2>/dev/null || true

python3 - <<'PY' "${full_dir}/raw_runs.csv" "${DATA_DIR:-data_cache/forex}" "${SESSION_START_UTC}" "${SESSION_END_UTC}" "${STRESS_SPREAD_MULT}" "${STRESS_SWAP_MULT}" "${MIN_MONTH_BOTH_PCT}" "${MIN_ROLL_BOTH_PCT}" "${REQUIRE_POS_MONTHS_GE_NEG}" "${MIN_MONTH_STRESS_TOTAL}" "${MIN_ROLL_STRESS_TOTAL}" "${ROLL_WINDOW_DAYS}" "${ROLL_STEP_DAYS}" "${STAB_MIN_TRADES}" "${STAB_MAX_DD}" "${STAB_MIN_NET}" "${STAB_MIN_RET_PCT}" "${RUN_DIR}/stability_report.csv" "${RUN_DIR}/stable_combos.txt"
import csv
import subprocess
import sys
from pathlib import Path

raw_csv = Path(sys.argv[1])
data_dir = Path(sys.argv[2])
session_start = int(sys.argv[3])
session_end = int(sys.argv[4])
stress_spread_mult = float(sys.argv[5])
stress_swap_mult = float(sys.argv[6])
min_month_both_pct = float(sys.argv[7])
min_roll_both_pct = float(sys.argv[8])
require_pos_ge_neg = int(sys.argv[9]) == 1
min_month_total = float(sys.argv[10])
min_roll_total = float(sys.argv[11])
roll_window = int(sys.argv[12])
roll_step = int(sys.argv[13])
stab_min_trades = int(sys.argv[14])
stab_max_dd = float(sys.argv[15])
stab_min_net = float(sys.argv[16])
stab_min_ret_pct = float(sys.argv[17])
out_csv = Path(sys.argv[18])
out_txt = Path(sys.argv[19])

def run_wf(symbol: str, strategy: str, mode: str):
    csv_path = data_dir / f"{symbol}_M5.csv"
    if not csv_path.exists():
        return None, f"missing_csv:{csv_path}"
    cmd = [
        "python3", "scripts/run_forex_combo_walkforward.py",
        "--symbol", symbol,
        "--csv", str(csv_path),
        "--strategy", strategy,
        "--mode", mode,
        "--session_start_utc", str(session_start),
        "--session_end_utc", str(session_end),
        "--stress_spread_mult", str(stress_spread_mult),
        "--stress_swap_mult", str(stress_swap_mult),
    ]
    if mode == "rolling":
        cmd += ["--window_days", str(roll_window), "--step_days", str(roll_step)]
    p = subprocess.run(cmd, text=True, capture_output=True)
    if p.returncode != 0:
        return None, f"wf_fail:{(p.stderr or p.stdout).strip()[:200]}"
    seg = ""
    summary = ""
    for line in p.stdout.splitlines():
        if line.startswith("segments_csv="):
            seg = line.split("=", 1)[1].strip()
        if line.startswith("summary_csv="):
            summary = line.split("=", 1)[1].strip()
    if not seg or not summary:
        return None, "wf_parse_fail"
    seg_path = Path(seg)
    sum_path = Path(summary)
    if not seg_path.exists() or not sum_path.exists():
        return None, "wf_output_missing"

    pos = neg = zero = 0
    with seg_path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v = float(r.get("stress_net_pips", "0") or 0)
            if v > 0:
                pos += 1
            elif v < 0:
                neg += 1
            else:
                zero += 1

    with sum_path.open(newline="", encoding="utf-8") as f:
        srow = next(csv.DictReader(f))
    return {
        "segments": int(float(srow.get("segments", "0") or 0)),
        "both_positive_share_pct": float(srow.get("both_positive_share_pct", "0") or 0),
        "stress_total": float(srow.get("total_stress_net_pips", "0") or 0),
        "stress_trades": int(float(srow.get("total_stress_trades", "0") or 0)),
        "pos_months": pos,
        "neg_months": neg,
        "zero_months": zero,
    }, ""

rows = []
seen = set()
with raw_csv.open(newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if (r.get("cost") or "").strip() != "stress":
            continue
        pair = (r.get("pair") or "").strip().upper()
        strategy = (r.get("strategy") or "").strip()
        if not pair or not strategy:
            continue
        key = (pair, strategy)
        if key in seen:
            continue
        seen.add(key)
        net = float(r.get("net_pips", "0") or 0)
        trades = int(float(r.get("trades", "0") or 0))
        dd = float(r.get("max_dd_pips", "0") or 0)
        ret = float(r.get("return_pct_est", "0") or 0)
        if net < stab_min_net:
            continue
        if trades < stab_min_trades:
            continue
        if dd > stab_max_dd:
            continue
        if ret < stab_min_ret_pct:
            continue
        rows.append({
            "pair": pair, "strategy": strategy, "stress_net": net, "stress_trades": trades,
            "stress_dd": dd, "stress_ret_pct": ret, "stress_ret_month_pct": float(r.get("return_pct_est_month", "0") or 0),
        })

report = []
stable = []
for base in rows:
    m, err_m = run_wf(base["pair"], base["strategy"], "monthly")
    rr, err_r = run_wf(base["pair"], base["strategy"], "rolling")
    status = "REJECT"
    reason = ""
    if err_m:
        reason = err_m
    elif err_r:
        reason = err_r
    else:
        checks = []
        checks.append(m["both_positive_share_pct"] >= min_month_both_pct)
        checks.append(rr["both_positive_share_pct"] >= min_roll_both_pct)
        checks.append(m["stress_total"] >= min_month_total)
        checks.append(rr["stress_total"] >= min_roll_total)
        if require_pos_ge_neg:
            checks.append(m["pos_months"] >= m["neg_months"])
        if all(checks):
            status = "PASS"
        else:
            parts = []
            if m["both_positive_share_pct"] < min_month_both_pct:
                parts.append("month_both_low")
            if rr["both_positive_share_pct"] < min_roll_both_pct:
                parts.append("roll_both_low")
            if m["stress_total"] < min_month_total:
                parts.append("month_total_low")
            if rr["stress_total"] < min_roll_total:
                parts.append("roll_total_low")
            if require_pos_ge_neg and m["pos_months"] < m["neg_months"]:
                parts.append("pos_lt_neg_months")
            reason = ",".join(parts) if parts else "checks_failed"

    row = dict(base)
    if m:
        row.update({
            "month_segments": m["segments"],
            "month_both_positive_share_pct": m["both_positive_share_pct"],
            "month_stress_total": m["stress_total"],
            "pos_months": m["pos_months"],
            "neg_months": m["neg_months"],
            "zero_months": m["zero_months"],
        })
    else:
        row.update({
            "month_segments": 0,
            "month_both_positive_share_pct": 0.0,
            "month_stress_total": 0.0,
            "pos_months": 0,
            "neg_months": 0,
            "zero_months": 0,
        })
    if rr:
        row.update({
            "roll_segments": rr["segments"],
            "roll_both_positive_share_pct": rr["both_positive_share_pct"],
            "roll_stress_total": rr["stress_total"],
        })
    else:
        row.update({
            "roll_segments": 0,
            "roll_both_positive_share_pct": 0.0,
            "roll_stress_total": 0.0,
        })
    row["status"] = status
    row["reason"] = reason
    report.append(row)
    if status == "PASS":
        stable.append(f"{row['pair']}@{row['strategy']}")

fields = [
    "pair","strategy","stress_net","stress_trades","stress_dd","stress_ret_pct","stress_ret_month_pct",
    "month_segments","month_both_positive_share_pct","month_stress_total","pos_months","neg_months","zero_months",
    "roll_segments","roll_both_positive_share_pct","roll_stress_total","status","reason"
]
with out_csv.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for r in sorted(report, key=lambda x: (x["status"] != "PASS", -x["stress_ret_month_pct"], -x["stress_ret_pct"], x["pair"], x["strategy"])):
        w.writerow(r)

with out_txt.open("w", encoding="utf-8") as f:
    if stable:
        f.write("\n".join(stable) + "\n")
    else:
        f.write("")

print(f"report_csv={out_csv}")
print(f"stable_txt={out_txt}")
print(f"stable_count={len(stable)}")
PY

cp "${RUN_DIR}/stability_report.csv" "${OUT_PREFIX}.csv"
cp "${RUN_DIR}/stable_combos.txt" "${OUT_PREFIX}.txt"

echo ""
echo "=== STABILITY PASS ==="
if [[ -s "${OUT_PREFIX}.txt" ]]; then
  cat "${OUT_PREFIX}.txt"
else
  echo "none"
fi

echo ""
echo "saved_dir=${RUN_DIR}"
echo "report=${OUT_PREFIX}.csv"
echo "stable=${OUT_PREFIX}.txt"
echo "forex stability gate done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
