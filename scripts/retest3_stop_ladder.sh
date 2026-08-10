#!/usr/bin/env bash
# RETEST V3 — САМЫЙ СИЛЬНЫЙ СЫРОЙ СИГНАЛ В ПРОЕКТЕ, ЗАДУШЕННЫЙ УЗКИМ СТОПОМ
#
#     nohup bash scripts/retest3_stop_ladder.sh > logs/retest3.log 2>&1 &
#
# ─────────────────────────────────────────────────────────────────────────────
# НАХОДКА 10 АВГУСТА
#
#   нога            стоп    удерж   валовой R/сд   издержки R/сд   чистый R/сд
#   inplay_retest_v3 1.14%   0.5ч      +0.1875        0.1053         +0.0850
#   ATT1             1.80%   5.8ч      +0.1672        0.0666         +0.0980
#   пробой уровня    1.88%   8.8ч      +0.0458        0.0638         -0.0210
#
# У retest_v3 САМЫЙ СИЛЬНЫЙ сырой сигнал во всём проекте — выше ATT1.
# И самые высокие издержки, потому что издержки в R = круг / ширина стопа,
# а стоп у неё 1.14% при удержании полчаса. Это скальп с ценой скальпа.
#
# ГИПОТЕЗА: расширение стопа опустит издержки быстрее, чем упадёт эдж.
#   стоп 1.14% -> 2.3%  даёт издержки ~0.052R вместо 0.105R
#   если валовой упадёт меньше чем на 0.05R/сд — нога переходит черту
#
# КАК ОНА УМРЁТ: валовой эдж упадёт пропорционально стопу или сильнее.
# Именно это случилось с ATT1: стоп 1.1 -> 2.2 ATR, издержки 0.066 -> 0.044,
# но эдж 0.098 -> 0.067. Там рычаг не сработал. Здесь запас больше,
# но исход не предрешён.
#
# ЛИМИТНЫЙ ВХОД ЗДЕСЬ НЕ ПРИМЕНЯЕМ. Замерено на этой же ноге:
# валовой +38.26R -> +13.66R. Причина механическая, см. ниже.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs backtest_runs

SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT,BNBUSDT,SUIUSDT,TAOUSDT,ONDOUSDT,WIFUSDT,1000PEPEUSDT}"
END_DATE="${END_DATE:-2026-06-30}"
DAYS="${DAYS:-540}"
CACHE_DIR="${CACHE_DIR:-data_cache}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export BACKTEST_CACHE_ONLY=1 BACKTEST_MIN_COVERAGE_FRAC=0.99

STOP_ENV="IRV3_STOP_BUFFER_ATR"
PREFLIGHT_ONLY="${RETEST3_PREFLIGHT_ONLY:-0}"
TAG_SUFFIX="${RETEST3_TAG_SUFFIX:-full540-v2}"
TAG_035="R3-stopbuf-035-$TAG_SUFFIX"
TAG_0525="R3-stopbuf-0525-$TAG_SUFFIX"
TAG_070="R3-stopbuf-070-$TAG_SUFFIX"
TAG_0875="R3-stopbuf-0875-$TAG_SUFFIX"
export TAG_035 TAG_0525 TAG_070 TAG_0875

# Fail before any long backtest if the runner and the strategy disagree about
# the environment contract. The previous version searched only for names that
# contained both "sl" and "atr", found nothing, and silently ran the baseline
# four times while exporting an unused RETEST3_STOP_MULT variable.
"$PYTHON_BIN" - <<'PY'
import json
import os

from strategies.inplay_retest_v3 import InplayRetestV3Strategy

expected = [0.35, 0.525, 0.70, 0.875]
resolved = []
for value in expected:
    os.environ["IRV3_STOP_BUFFER_ATR"] = str(value)
    actual = float(InplayRetestV3Strategy().cfg.stop_buffer_atr)
    if abs(actual - value) > 1e-12:
        raise SystemExit(
            f"stop handle mismatch: requested={value} resolved={actual}"
        )
    resolved.append(actual)

if len(set(resolved)) != len(expected):
    raise SystemExit(f"stop handle does not differentiate variants: {resolved}")

print(json.dumps({
    "schema_id": "retest3_stop_ladder_preflight_v1",
    "env": "IRV3_STOP_BUFFER_ATR",
    "resolved_stop_buffer_atr": resolved,
}, sort_keys=True))
PY

echo "ручка стопа: $STOP_ENV (preflight PASS)"
if [ "$PREFLIGHT_ONLY" = "1" ]; then
  echo "RETEST3_PREFLIGHT_ONLY=1 — полные прогоны не запускались"
  exit 0
fi

run_stop () {
  local tag="$1"; local stop_buffer_atr="$2"
  if ls backtest_runs/*_"$tag"/trades.csv >/dev/null 2>&1; then
    echo ">>> $tag уже есть"; return 0
  fi
  echo ">>> $tag  $STOP_ENV=$stop_buffer_atr  $(date -u '+%H:%M:%S')"
  ( export IRV3_STOP_BUFFER_ATR="$stop_buffer_atr"
    "$PYTHON_BIN" backtest/run_portfolio.py \
      --symbols "$SYMBOLS" --days "$DAYS" --end "$END_DATE" \
      --starting_equity 1000 --risk_pct 0.0075 --leverage 1 --max_positions 3 \
      --fee_bps 6 --slippage_bps 2 --entry-on-next-open \
      --cap_notional 317 --cache "$CACHE_DIR" \
      --strategies inplay_retest_v3 --tag "$tag" ) 2>&1 | tail -3
}

# New tags deliberately quarantine the earlier broken R3-stop-* outputs. A
# caller can use RETEST3_TAG_SUFFIX=smoke90-v1 for a bounded differentiating
# smoke without poisoning or suppressing the full 540-day tags.
run_stop "$TAG_035" 0.35
run_stop "$TAG_0525" 0.525
run_stop "$TAG_070" 0.70
run_stop "$TAG_0875" 0.875

echo
echo "════════ АУДИТ ════════"
"$PYTHON_BIN" scripts/audit_backtest_run.py \
  "$TAG_035" "$TAG_0525" "$TAG_070" "$TAG_0875" \
  2>&1 | grep -E "^====|СТОП|ВНИМ|──"

echo
echo "════════ РЕЗУЛЬТАТ ════════"
"$PYTHON_BIN" - <<'PY'
import csv, glob, os, statistics as st
print(f"{'вариант':<16}{'сд.':>5}{'стоп%':>8}{'валовой':>10}{'изд.':>8}{'чистый':>9}{'R/сд':>9}{'t':>7}")
medians=[]
for tag in [os.environ["TAG_035"], os.environ["TAG_0525"],
            os.environ["TAG_070"], os.environ["TAG_0875"]]:
    d=sorted(glob.glob(f"backtest_runs/*_{tag}/trades.csv"))
    if not d: print(f"{tag:<16}  нет результата"); continue
    rows=[r for r in csv.DictReader(open(d[-1])) if float(r.get("initial_risk_usd") or 0)>0]
    if not rows: print(f"{tag:<16}  0 сделок"); continue
    g=[(float(r["pnl"])+float(r["fees"]))/float(r["initial_risk_usd"]) for r in rows]
    n=[float(r["pnl"])/float(r["initial_risk_usd"]) for r in rows]
    f=[float(r["fees"])/float(r["initial_risk_usd"]) for r in rows]
    stop=[abs(float(r["entry_price"])-float(r["initial_sl"]))/float(r["entry_price"])*100
          for r in rows if float(r.get("initial_sl") or 0)>0]
    m=st.mean(n); sd=st.stdev(n) if len(n)>1 else 0.0
    t=m/(sd/len(n)**0.5) if sd>0 else 0.0
    median_stop=st.median(stop)
    medians.append(round(median_stop, 6))
    print(f"{tag:<16}{len(rows):>5}{st.median(stop):>8.2f}{sum(g):>+10.2f}"
          f"{st.median(f):>8.4f}{sum(n):>+9.2f}{m:>+9.4f}{t:>+7.2f}")
if len(medians) != 4 or len(set(medians)) != 4:
    raise SystemExit(
        "\n!!! STOP DISTRIBUTIONS НЕ РАЗЛИЧАЮТСЯ — результат запрещён к интерпретации: "
        + repr(medians)
    )
print("\nSTOP DISTRIBUTION DIFFERENCE: PASS " + repr(medians))
print("ЭТАЛОН: ATT1 пологие+лимит +0.3203R/сд t=+2.26 | ATT1 эталон +0.0980 t=+1.66")
print("Кандидат: R/сд > 0.06 при t > 1.5. Дальше — окно 2024-07..2025-01.")
PY
touch logs/retest3.done
