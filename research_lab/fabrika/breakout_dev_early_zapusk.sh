#!/bin/bash
# Один прогон DEV_EARLY (prereg bc442fe, раннер dcfa5a6): 13 монет × 3 сегмента, 4 параллельно, затем вердикт.
cd "$(dirname "$0")/../.." || exit 1
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
for s in 2023H1 2023H2 2024H1; do for m in 1000PEPEUSDT ADAUSDT AVAXUSDT BNBUSDT BTCUSDT DOGEUSDT ETHUSDT ONDOUSDT SOLUSDT SUIUSDT TAOUSDT WIFUSDT XRPUSDT; do echo "$s $m"; done; done \
 | xargs -P4 -L1 sh -c "$PY research_lab/fabrika/breakout_dev_early.py --zadacha \$0 \$1"
$PY research_lab/fabrika/breakout_dev_early.py --itog
echo "ГОТОВО $(date -u)"
