#!/bin/bash
# podnyat_vse.sh — поднять ВСЕ тени, сборщики и сторожа после перезагрузки Мака (13.10.2026).
# Безопасно запускать сколько угодно раз: каждый процесс идёт через fabrika/edinstvennyy_zapusk.py (pgrep + замок),
# уже работающий второй раз не стартует. ETS2S/ATT1 — через старый podnyat_teni.sh (свой PID-замок).
# Не поднимает: pump4 (мёртв с 08.09), bitget_vpered (BLOCKED_DATA), Ollama/ИИ (только вручную по отдельному решению).
cd "$(dirname "$0")/.." || exit 1
PY=.venv/bin/python; L=research_lab/fabrika/edinstvennyy_zapusk.py; D=research_lab/data
[ -x "$PY" ] && "$PY" -c 'import numpy' 2>/dev/null || { echo "НЕТ .venv с numpy — ничего не поднято"; exit 1; }
up () { # up <имя> <журнал> <команда...>
  N="$1"; LOG="$2"; shift 2
  screen -dmS "$N" sh -c "$PY $L $N -- caffeinate -i $* >> $LOG 2>&1"
  echo "  $N → $LOG"
}
echo "ПОДНИМАЮ $(date '+%F %T')"
up atlas        $D/kripto_atlas.log        $PY research_lab/fabrika/kripto_atlas_sbor.py --cikl
up kity_bybit   $D/kity_bybit_ten.log      $PY research_lab/kity_bybit_ten.py --cikl
up kity_m3      $D/kity_m3_ten.log         $PY research_lab/kity_m3_ten.py --cikl
up yadro_ETS2M  $D/yadro_ETS2M.log         $PY research_lab/yadro.py --epoha ETS2M --minut 100000 --pauza 3600
up breakout     $D/breakout_ten.log        $PY research_lab/breakout_ten.py --cikl
up bounce1      $D/bounce_ten_BOUNCE1.log  $PY research_lab/bounce_ten.py --variant BOUNCE1 --cikl
up bounce1_8    $D/bounce_ten_BOUNCE1_8.log $PY research_lab/bounce_ten.py --variant BOUNCE1_8 --cikl
up poly         $D/poly/snimki.log         $PY research_lab/fabrika/poly_sbor.py --snimki 15
up sila         $D/ten_SILA.log            .venv-research/bin/python research_lab/ten_sila.py --minut 100000 --pauza 21600
screen -dmS rebal sh -c "cd signal_copy && ../$PY ../$L rebal -- caffeinate -i ../$PY ../research_lab/rebal_ten.py --cikl >> ../$D/rebal_ten.log 2>&1"; echo "  rebal"
up storozh      $D/storozh/storozh_stdout.log $PY research_lab/fabrika/storozh.py --cikl
for S in dynamic_shadow post_n42_frozen; do   # v4_shadow мёртв с 04.08 — не воскрешаем
  pgrep -f "run_funding_positioning_${S}_loop.sh" >/dev/null || { screen -dmS "research_funding_$S" /bin/bash -lc "scripts/run_funding_positioning_${S}_loop.sh"; echo "  funding $S"; }
done
bash research_lab/podnyat_teni.sh | sed 's/^/  /'
sleep 5; echo "screen-сессии:"; screen -ls | grep -E "\.(atlas|kity|yadro|breakout|bounce|poly|sila|rebal|storozh|research_funding)" | sed 's/^/  /'
echo "Через 10–15 минут Claude проверит сторожем."
