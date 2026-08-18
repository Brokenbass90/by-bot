#!/bin/bash
cd "$(dirname "$0")/.."
L=research_lab/conc.log
: > $L
nice -n 15 python3 research_lab/concentration.py sloped_break_retest_v1 SlopedBreakRetestV1Strategy SBR1 short 1.0 336 "флет-" 0 2>&1 | grep -v "^\.\.\." >> $L
nice -n 15 python3 research_lab/concentration.py alt_trendline_touch_v1 AltTrendlineTouchV1Strategy ATT1 short 6.0 336 "флет-" 8 2>&1 | grep -v "^\.\.\." >> $L
echo "=== ГОТОВО $(date -u)" >> $L
