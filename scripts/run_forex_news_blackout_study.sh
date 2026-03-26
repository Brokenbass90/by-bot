#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SYMBOL="${FX_SYMBOL:-GBPJPY}"
CSV_PATH="${FX_CSV_PATH:-data_cache/forex/${SYMBOL}_M5.csv}"
STRATEGY="${FX_STRATEGY:-trend_retest_session_v2:conservative}"
SESSION_START="${FX_SESSION_START_UTC:-6}"
SESSION_END="${FX_SESSION_END_UTC:-14}"
MIN_BARS="${FX_MIN_BARS:-600}"
ROLLING_WINDOW_DAYS="${FX_ROLLING_WINDOW_DAYS:-28}"
ROLLING_STEP_DAYS="${FX_ROLLING_STEP_DAYS:-7}"
NEWS_EVENTS_CSV="${FX_NEWS_EVENTS_CSV:-runtime/news_filter/events_latest.csv}"
NEWS_POLICY_JSON="${FX_NEWS_POLICY_JSON:-configs/news_filter_policy.example.json}"
TAG_BASE="${FX_NEWS_STUDY_TAG:-${SYMBOL,,}_news_study}"

echo "symbol=$SYMBOL strategy=$STRATEGY"
echo "csv=$CSV_PATH"
echo "news_events_csv=$NEWS_EVENTS_CSV"
echo "news_policy_json=$NEWS_POLICY_JSON"

python3 scripts/run_forex_combo_walkforward.py \
  --symbol "$SYMBOL" \
  --csv "$CSV_PATH" \
  --strategy "$STRATEGY" \
  --tag "${TAG_BASE}_baseline" \
  --mode monthly \
  --min_bars "$MIN_BARS" \
  --session_start_utc "$SESSION_START" \
  --session_end_utc "$SESSION_END"

python3 scripts/run_forex_combo_walkforward.py \
  --symbol "$SYMBOL" \
  --csv "$CSV_PATH" \
  --strategy "$STRATEGY" \
  --tag "${TAG_BASE}_baseline" \
  --mode rolling \
  --window_days "$ROLLING_WINDOW_DAYS" \
  --step_days "$ROLLING_STEP_DAYS" \
  --min_bars "$MIN_BARS" \
  --session_start_utc "$SESSION_START" \
  --session_end_utc "$SESSION_END"

python3 scripts/run_forex_combo_walkforward.py \
  --symbol "$SYMBOL" \
  --csv "$CSV_PATH" \
  --strategy "$STRATEGY" \
  --tag "${TAG_BASE}_news" \
  --mode monthly \
  --min_bars "$MIN_BARS" \
  --session_start_utc "$SESSION_START" \
  --session_end_utc "$SESSION_END" \
  --news-events-csv "$NEWS_EVENTS_CSV" \
  --news-policy-json "$NEWS_POLICY_JSON"

python3 scripts/run_forex_combo_walkforward.py \
  --symbol "$SYMBOL" \
  --csv "$CSV_PATH" \
  --strategy "$STRATEGY" \
  --tag "${TAG_BASE}_news" \
  --mode rolling \
  --window_days "$ROLLING_WINDOW_DAYS" \
  --step_days "$ROLLING_STEP_DAYS" \
  --min_bars "$MIN_BARS" \
  --session_start_utc "$SESSION_START" \
  --session_end_utc "$SESSION_END" \
  --news-events-csv "$NEWS_EVENTS_CSV" \
  --news-policy-json "$NEWS_POLICY_JSON"
