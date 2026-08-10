#!/usr/bin/env bash
# ATT1 ПОЛОГИЕ ЛИНИИ + ЛИМИТНЫЙ ВХОД — проверка на окне 2024-07..2025-01
#
#     nohup bash scripts/att1_shallow_oos.sh > logs/att1_shallow.log 2>&1 &
#     готовность:  ls logs/att1_shallow.done
#
# ─────────────────────────────────────────────────────────────────────────────
# ПРЕДРЕГИСТРАЦИЯ  trial 0ad77b93e3a5  (research_lab/trial_ledger.py)
#
# ГИПОТЕЗА
#   ATT1 с ATT1_MAX_SLOPE_PCT=0.7 и лимитным входом положительна
#   на окне 2024-07-15..2025-01-06.
#
# КАК ОНА УМРЁТ — объявлено ДО прогона и не смягчается после:
#   чистый R <= 0  ЛИБО  R/сделку < 0.06  ЛИБО  t < 1.5
#
# ЧТО ЗАМЕРЕНО НА ОКНЕ 2025-01..2026-06 (то самое, где подбирался порог)
#   ATT1 эталон              308 сд.  +0.0980R/сд  t=+1.66
#   ATT1 пологие + лимит      53 сд.  +0.3203R/сд  t=+2.26
#
# ЧЕСТНО ПРО НЕЗАВИСИМОСТЬ
#   Окно 2024H2 уже использовалось для проверки книги целиком.
#   Но порог наклона 0.7 на нём НЕ подбирался — он выведен из градиента
#   на другом окне. Это ЧАСТИЧНАЯ независимость, и называть её чистым
#   holdout нельзя. Чистого holdout для ATT1 не осталось вообще.
#
# ЧЕГО ЖДАТЬ ПО РАЗМЕРУ ВЫБОРКИ
#   На 540 днях фильтр оставил 53 сделки из 308. На 175 днях это
#   примерно 15-20 сделок. При таком n t выше 1.5 маловероятен даже
#   при настоящем эдже. Поэтому вероятный исход — «не доказано»,
#   а не «опровергнуто», и это надо различать: критерий убивает
#   гипотезу, но малый n убивает не её, а нашу способность судить.
#
# ЗАЧЕМ ТОГДА ГОНЯТЬ
#   Знак и величина R/сделку информативны сами по себе. Если на чужом
#   окне выйдет заметный минус — гипотеза мертва по существу. Если
#   плюс похожего масштаба при малом t — это слабое подтверждение,
#   и тогда решает не этот прогон, а данные от Codex.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs backtest_runs

SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT,BNBUSDT,SUIUSDT,TAOUSDT,ONDOUSDT,WIFUSDT,1000PEPEUSDT}"
END_DATE="${END_DATE:-2025-01-06}"
DAYS="${DAYS:-175}"
CACHE_DIR="${CACHE_DIR:-data_cache}"
export BACKTEST_CACHE_ONLY=1 BACKTEST_MIN_COVERAGE_FRAC=0.99

# ── ПРЕДПОЛЁТ: ручка наклона обязана реально менять конфиг ────────────────
python3 - <<'PY' || { echo "!!! ПРЕДПОЛЁТ НЕ ПРОЙДЕН — прогон не начат"; exit 1; }
import sys
sys.path.insert(0, ".")
from research_lab.experiment_preflight import assert_handle_differentiates, PreflightError
try:
    assert_handle_differentiates("alt_trendline_touch_v1", "ATT1_MAX_SLOPE_PCT",
                                 "max_slope_pct", [0.7, 4.0])
except PreflightError as e:
    print(f"FAIL: {e}"); raise SystemExit(1)
PY

base_env () {
  export ATT1_ALLOW_LONGS=0 ATT1_ALLOW_SHORTS=1 ATT1_MIN_PIVOTS=2 \
         ATT1_MAX_PIVOT_AGE=16 ATT1_MIN_R2=0.55 ATT1_TOUCH_ATR=0.5 \
         ATT1_PIVOT_LEFT=2 ATT1_PIVOT_RIGHT=3
}

run_case () {
  local tag="$1"; shift
  if ls backtest_runs/*_"$tag"/trades.csv >/dev/null 2>&1; then
    echo ">>> $tag уже есть"; return 0
  fi
  echo ">>> $tag  $(date -u '+%H:%M:%S')   $*"
  ( base_env; export "$@" 2>/dev/null || true
    python3 backtest/run_portfolio.py \
      --symbols "$SYMBOLS" --days "$DAYS" --end "$END_DATE" \
      --starting_equity 1000 --risk_pct 0.0075 --leverage 1 --max_positions 3 \
      --fee_bps 6 --slippage_bps 2 --entry-on-next-open \
      --cap_notional 317 --cache "$CACHE_DIR" \
      --strategies alt_trendline_touch_v1 --tag "$tag" ) 2>&1 | tail -3
}

# эталон нужен, чтобы отличить «фильтр помог» от «окно само по себе хорошее»
run_case OOS24-att1-base   NOOP=1
run_case OOS24-att1-shallow ATT1_MAX_SLOPE_PCT=0.7
run_case OOS24-att1-shallow-maker ATT1_MAX_SLOPE_PCT=0.7 BACKTEST_MAKER_ENTRY=1

echo
echo "════════ АУДИТ ════════"
python3 scripts/audit_backtest_run.py OOS24-att1-base OOS24-att1-shallow OOS24-att1-shallow-maker 2>&1 | grep -E "^====|СТОП|ВНИМ|──"

echo
echo "════════ ВЕРДИКТ ПО ПРЕДРЕГИСТРАЦИИ  trial 0ad77b93e3a5 ════════"
python3 - <<'PY'
import csv, glob, statistics as st

def stats(tag):
    d = sorted(glob.glob(f"backtest_runs/*_{tag}/trades.csv"))
    if not d: return None
    rows = [r for r in csv.DictReader(open(d[-1])) if float(r.get("initial_risk_usd") or 0) > 0]
    if not rows: return None
    g = [(float(r["pnl"]) + float(r["fees"])) / float(r["initial_risk_usd"]) for r in rows]
    n = [float(r["pnl"]) / float(r["initial_risk_usd"]) for r in rows]
    m = st.mean(n); sd = st.stdev(n) if len(n) > 1 else 0.0
    t = m / (sd / len(n) ** 0.5) if sd > 0 else 0.0
    return dict(n=len(rows), gross=sum(g), net=sum(n), per=m, t=t)

print(f"{'вариант':<28}{'сд.':>5}{'валовой':>10}{'чистый':>9}{'R/сд':>10}{'t':>7}")
res = {}
for tag, lbl in [("OOS24-att1-base", "ATT1 эталон"),
                 ("OOS24-att1-shallow", "ATT1 пологие"),
                 ("OOS24-att1-shallow-maker", "ATT1 пологие + лимит")]:
    s = stats(tag); res[tag] = s
    if not s: print(f"{lbl:<28}  нет результата"); continue
    print(f"{lbl:<28}{s['n']:>5}{s['gross']:>+10.2f}{s['net']:>+9.2f}{s['per']:>+10.4f}{s['t']:>+7.2f}")

s = res.get("OOS24-att1-shallow-maker")
print()
if not s:
    print("нет результата — вердикт невозможен")
elif s["n"] < 12:
    print(f"СЛИШКОМ МАЛО СДЕЛОК ({s['n']}) — это НЕ опровержение и НЕ подтверждение.")
    print("Судить нельзя; решает объём данных, а не эта гипотеза.")
elif s["net"] <= 0 or s["per"] < 0.06 or s["t"] < 1.5:
    print(f"ОПРОВЕРГНУТА по объявленному заранее критерию "
          f"(чистый {s['net']:+.2f}R, {s['per']:+.4f}R/сд, t={s['t']:+.2f})")
else:
    print(f"ВЫЖИЛА: {s['per']:+.4f}R/сд, t={s['t']:+.2f} на {s['n']} сделках.")
    print("Дальше — выделение горизонтального отбоя в отдельную ногу.")
print()
print("ЭТАЛОН на окне подбора 2025-01..2026-06: пологие+лимит +0.3203R/сд t=+2.26")
PY
touch logs/att1_shallow.done
