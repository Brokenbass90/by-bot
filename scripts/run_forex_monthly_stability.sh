#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

ACTIVE_COMBOS_TXT="${FX_ACTIVE_COMBOS_TXT:-docs/forex_combo_active_latest.txt}"
DATA_DIR="${FX_DATA_DIR:-data_cache/forex}"
SESSION_START_UTC="${FX_SESSION_START_UTC:-6}"
SESSION_END_UTC="${FX_SESSION_END_UTC:-20}"
STRESS_SPREAD_MULT="${FX_STRESS_SPREAD_MULT:-1.5}"
STRESS_SWAP_MULT="${FX_STRESS_SWAP_MULT:-1.5}"
OUT_PREFIX="${FX_OUT_PREFIX:-docs/forex_monthly_stability_latest}"

echo "forex monthly stability start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "active_combos=${ACTIVE_COMBOS_TXT}"
echo "data_dir=${DATA_DIR}"
echo "session_utc=[${SESSION_START_UTC},${SESSION_END_UTC})"
echo "stress_multipliers: spread=${STRESS_SPREAD_MULT} swap=${STRESS_SWAP_MULT}"

if [[ ! -f "${ACTIVE_COMBOS_TXT}" ]]; then
  echo "missing active combos file: ${ACTIVE_COMBOS_TXT}"
  exit 1
fi

tmp_csv="$(mktemp)"
tmp_txt="$(mktemp)"

echo "pair,strategy,segments,pos_months,neg_months,zero_months,both_positive_share_pct,total_stress_net_pips,total_stress_trades,status" > "${tmp_csv}"

while IFS= read -r combo || [[ -n "${combo}" ]]; do
  combo="${combo//$'\r'/}"
  if [[ -z "${combo}" ]]; then
    continue
  fi
  if [[ "${combo}" =~ ^# ]]; then
    continue
  fi

  pair="${combo%@*}"
  strategy="${combo#*@}"
  csv_path="${DATA_DIR}/${pair}_M5.csv"

  if [[ ! -f "${csv_path}" ]]; then
    echo "${pair},${strategy},0,0,0,0,0,0,0,missing_csv" >> "${tmp_csv}"
    echo "MISS ${pair}@${strategy} | csv not found: ${csv_path}" >> "${tmp_txt}"
    continue
  fi

  run_out="$(python3 scripts/run_forex_combo_walkforward.py \
    --symbol "${pair}" \
    --csv "${csv_path}" \
    --strategy "${strategy}" \
    --mode monthly \
    --session_start_utc "${SESSION_START_UTC}" \
    --session_end_utc "${SESSION_END_UTC}" \
    --stress_spread_mult "${STRESS_SPREAD_MULT}" \
    --stress_swap_mult "${STRESS_SWAP_MULT}" 2>&1 || true)"

  segments_csv="$(printf '%s\n' "${run_out}" | awk -F= '/^segments_csv=/{print $2}' | tail -n 1)"
  summary_csv="$(printf '%s\n' "${run_out}" | awk -F= '/^summary_csv=/{print $2}' | tail -n 1)"

  if [[ -z "${segments_csv}" || -z "${summary_csv}" || ! -f "${segments_csv}" || ! -f "${summary_csv}" ]]; then
    err_line="$(printf '%s\n' "${run_out}" | tail -n 1 | tr ',' ' ')"
    echo "${pair},${strategy},0,0,0,0,0,0,0,error" >> "${tmp_csv}"
    echo "ERR  ${pair}@${strategy} | ${err_line}" >> "${tmp_txt}"
    continue
  fi

  read -r pos_months neg_months zero_months < <(
    awk -F',' '
      NR>1 {
        v=$8+0
        if (v>0) pos++
        else if (v<0) neg++
        else zero++
      }
      END {
        if (pos=="") pos=0
        if (neg=="") neg=0
        if (zero=="") zero=0
        printf "%d %d %d\n", pos, neg, zero
      }
    ' "${segments_csv}"
  )

  read -r segments both_share stress_total stress_trades < <(
    awk -F',' 'NR==2 {printf "%s %s %s %s\n", $4, $6, $8, $12}' "${summary_csv}"
  )

  echo "${pair},${strategy},${segments},${pos_months},${neg_months},${zero_months},${both_share},${stress_total},${stress_trades},ok" >> "${tmp_csv}"
  echo "OK   ${pair}@${strategy} | months +${pos_months}/-${neg_months}/0:${zero_months} | both+=${both_share}% | stress_total=${stress_total}" >> "${tmp_txt}"
done < "${ACTIVE_COMBOS_TXT}"

mkdir -p "$(dirname "${OUT_PREFIX}")"
cp "${tmp_csv}" "${OUT_PREFIX}.csv"
cp "${tmp_txt}" "${OUT_PREFIX}.txt"

echo ""
cat "${OUT_PREFIX}.txt"
echo ""
echo "saved_csv=${OUT_PREFIX}.csv"
echo "saved_txt=${OUT_PREFIX}.txt"
echo "forex monthly stability done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"

rm -f "${tmp_csv}" "${tmp_txt}"

