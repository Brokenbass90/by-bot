#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

SCAN_SUMMARY="${EQ_SCAN_SUMMARY:-}"
if [[ -z "${SCAN_SUMMARY}" ]]; then
  latest_dir="$(ls -1dt backtest_runs/equities_scan_* 2>/dev/null | head -n 1 || true)"
  if [[ -z "${latest_dir}" ]]; then
    echo "No equities_scan runs found under backtest_runs/"
    exit 1
  fi
  SCAN_SUMMARY="${latest_dir}/summary.csv"
fi

if [[ ! -f "${SCAN_SUMMARY}" ]]; then
  echo "scan summary not found: ${SCAN_SUMMARY}"
  exit 1
fi

DATA_DIR="${EQ_DATA_DIR:-data_cache/equities}"
SESSION_START="${EQ_SESSION_START_UTC:-14}"
SESSION_END="${EQ_SESSION_END_UTC:-21}"
BASE_SPREAD_CENTS="${EQ_BASE_SPREAD_CENTS:-2.0}"
STRESS_SPREAD_MULT="${EQ_STRESS_SPREAD_MULT:-1.75}"
PIP_SIZE="${EQ_PIP_SIZE:-0.01}"
MIN_TRADES="${EQ_WF_MIN_TRADES:-20}"
TOP_N="${EQ_WF_TOP_N:-8}"
MIN_SEGMENTS="${EQ_WF_MIN_SEGMENTS:-5}"
MIN_BOTH_POS_PCT="${EQ_WF_MIN_BOTH_POS_PCT:-55}"
MIN_STRESS_TOTAL="${EQ_WF_MIN_STRESS_TOTAL:-0}"
START_DATE="${EQ_WF_START_DATE:-${EQ_START_DATE:-}}"
END_DATE="${EQ_WF_END_DATE:-${EQ_END_DATE:-}}"
RUN_SUFFIX="${EQ_WF_RUN_SUFFIX:-${EQ_RUN_SUFFIX:-}}"

STAMP="$(date -u +%Y%m%d_%H%M%S)"
if [[ -n "${RUN_SUFFIX}" ]]; then
  OUT_DIR="backtest_runs/equities_wf_gate_${STAMP}_${RUN_SUFFIX}"
else
  OUT_DIR="backtest_runs/equities_wf_gate_${STAMP}"
fi
mkdir -p "${OUT_DIR}"
RAW_CSV="${OUT_DIR}/raw_walkforward.csv"
PASS_CSV="${OUT_DIR}/gated_walkforward.csv"
echo "ticker,strategy,segments,both_positive_segments,both_positive_share_pct,total_base_net_cents,total_stress_net_cents,total_base_trades,total_stress_trades,run_dir,status,error" > "${RAW_CSV}"
CANDIDATES=()

echo "equities walkforward gate start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "scan_summary=${SCAN_SUMMARY}"
echo "data_dir=${DATA_DIR}"
echo "date_range=${START_DATE:-full}..${END_DATE:-full}"

while IFS= read -r line; do
  [[ -n "${line}" ]] && CANDIDATES+=("${line}")
done < <(python3 - "${SCAN_SUMMARY}" "${MIN_TRADES}" "${TOP_N}" <<'PY'
import csv,sys
from pathlib import Path
p=Path(sys.argv[1])
min_tr=float(sys.argv[2]); top_n=max(1,int(sys.argv[3]))
rows=[]
with p.open(newline='', encoding='utf-8') as f:
    r=csv.DictReader(f)
    for row in r:
        if row.get("base_status")!="ok" or row.get("stress_status")!="ok":
            continue
        bt=float(row.get("base_trades") or 0)
        st=float(row.get("stress_trades") or 0)
        bn=float(row.get("base_net_cents") or 0)
        sn=float(row.get("stress_net_cents") or 0)
        if bt < min_tr or st < min_tr:
            continue
        if bn <= 0 or sn <= 0:
            continue
        rows.append((sn, row.get("ticker","").upper(), row.get("strategy","")))
rows.sort(reverse=True, key=lambda x:x[0])
for _,t,s in rows[:top_n]:
    if t and s:
        print(f"{t},{s}")
PY
)

if [[ ${#CANDIDATES[@]} -eq 0 ]]; then
  echo "No candidates from scan passed prefilter"
  echo "raw=${RAW_CSV}"
  exit 0
fi

for item in "${CANDIDATES[@]}"; do
  ticker="${item%%,*}"
  strategy="${item#*,}"
  csv_path="${DATA_DIR}/${ticker}_M5.csv"
  if [[ ! -f "${csv_path}" ]]; then
    echo "${ticker},${strategy},0,0,0,0,0,0,0,,skip,missing_csv" >> "${RAW_CSV}"
    continue
  fi

  tag="eqwf_${ticker}_${strategy}_$(date -u +%Y%m%d_%H%M%S)"
  log="${OUT_DIR}/${ticker}_${strategy}.log"
  if python3 scripts/run_forex_combo_walkforward.py \
      --symbol "${ticker}" \
      --csv "${csv_path}" \
      --strategy "${strategy}" \
      --tag "${tag}" \
      ${START_DATE:+--start-date "$START_DATE"} \
      ${END_DATE:+--end-date "$END_DATE"} \
      --mode rolling \
      --window_days 14 \
      --step_days 5 \
      --min_bars 180 \
      --session_start_utc "${SESSION_START}" \
      --session_end_utc "${SESSION_END}" \
      --pip_size "${PIP_SIZE}" \
      --spread_pips "${BASE_SPREAD_CENTS}" \
      --swap_pips 0 \
      --stress_spread_mult "${STRESS_SPREAD_MULT}" \
      --stress_swap_mult 1.0 > "${log}" 2>&1; then

    run_dir="$(grep -E '^segments_csv=' "${log}" | tail -n 1 | sed 's#segments_csv=##' | xargs dirname)"
    summary_csv="${run_dir}/summary.csv"
    if [[ ! -f "${summary_csv}" ]]; then
      echo "${ticker},${strategy},0,0,0,0,0,0,0,${run_dir},fail,missing_summary" >> "${RAW_CSV}"
      continue
    fi

    metrics="$(python3 - "${summary_csv}" <<'PY'
import csv,sys
with open(sys.argv[1], newline='', encoding='utf-8') as f:
    r=csv.DictReader(f); row=next(r,{})
print(",".join([
    row.get("segments","0"),
    row.get("both_positive_segments","0"),
    row.get("both_positive_share_pct","0"),
    row.get("total_base_net_pips","0"),
    row.get("total_stress_net_pips","0"),
    row.get("total_base_trades","0"),
    row.get("total_stress_trades","0"),
]))
PY
)"
    IFS=',' read -r segments both_pos both_pct base_total stress_total base_trades stress_trades <<< "${metrics}"
    echo "${ticker},${strategy},${segments},${both_pos},${both_pct},${base_total},${stress_total},${base_trades},${stress_trades},${run_dir},ok," >> "${RAW_CSV}"
  else
    err="$(tail -n 1 "${log}" | tr ',' ';')"
    echo "${ticker},${strategy},0,0,0,0,0,0,0,,fail,${err}" >> "${RAW_CSV}"
  fi
done

python3 - "${RAW_CSV}" "${PASS_CSV}" "${MIN_SEGMENTS}" "${MIN_BOTH_POS_PCT}" "${MIN_STRESS_TOTAL}" <<'PY'
import csv,sys
from pathlib import Path
raw=Path(sys.argv[1]); out=Path(sys.argv[2])
min_segments=float(sys.argv[3]); min_both=float(sys.argv[4]); min_stress=float(sys.argv[5])
rows=[]
with raw.open(newline='', encoding='utf-8') as f:
    r=csv.DictReader(f)
    for row in r:
        if row.get("status")!="ok":
            continue
        seg=float(row.get("segments") or 0)
        both=float(row.get("both_positive_share_pct") or 0)
        stress=float(row.get("total_stress_net_cents") or 0)
        if seg < min_segments or both < min_both or stress <= min_stress:
            continue
        row["_stress"]=stress
        rows.append(row)
rows.sort(key=lambda x:x["_stress"], reverse=True)
with out.open("w", newline="", encoding="utf-8") as f:
    w=csv.DictWriter(f, fieldnames=[
        "ticker","strategy","segments","both_positive_segments","both_positive_share_pct",
        "total_base_net_cents","total_stress_net_cents","total_base_trades","total_stress_trades","run_dir","status","error"
    ])
    w.writeheader()
    for row in rows:
        row.pop("_stress", None)
        w.writerow(row)
print(f"passes={len(rows)}")
PY

echo ""
echo "=== WALKFORWARD GATE PASS ==="
python3 - "${PASS_CSV}" <<'PY'
import csv,sys
from pathlib import Path
p=Path(sys.argv[1])
with p.open(newline='', encoding='utf-8') as f:
    r=csv.DictReader(f)
    rows=list(r)
if not rows:
    print("no pass")
else:
    for row in rows:
        print(f"{row['ticker']:>6} {row['strategy']:<32} both+={row['both_positive_share_pct']}% stress_total={float(row['total_stress_net_cents']):+8.2f} seg={row['segments']} trades={row['total_stress_trades']}")
PY

echo ""
echo "equities walkforward gate done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "raw=${RAW_CSV}"
echo "gated=${PASS_CSV}"
