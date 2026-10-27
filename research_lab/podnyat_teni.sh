#!/bin/bash
# podnyat_teni.sh — поднять все тени. Безопасно запускать сколько угодно раз:
# у каждой тени свой замок по PID, вторая копия сама откажется работать.
#
# Пропуск в работе НЕ теряет данные: каждый проход заново качает 1000
# часовых баров (41 день), поэтому сигналы из перерыва всё равно находятся.
# Момент старта тени записан на диск и при перезапуске не сбрасывается.
cd "$(dirname "$0")/.." || exit 1
KOREN="$(pwd)"

# ВЫБОР ПИТОНА. Дефект 14 сентября: скрипт звал просто `python3`, и в
# терминале без активированного окружения тени поднялись системным
# питоном, упали на `No module named numpy` и молча умерли. Первым
# попавшимся интерпретатором больше не запускаемся.
#
# Правило: берём первый, у которого numpy ЕСТЬ. Если такого нет —
# не поднимаем ничего и говорим об этом громко. Мёртвая тень хуже
# отсутствующей: она выглядит как работающая.
PY=""
for K in "$KOREN/.venv/bin/python3" \
         "$HOME/.pyenv/versions/3.11.9/bin/python3" \
         "$(command -v python3)"; do
  [ -x "$K" ] || continue
  if "$K" -c 'import numpy' >/dev/null 2>&1; then PY="$K"; break; fi
done
if [ -z "$PY" ]; then
  echo "НЕ НАШЁЛ ПИТОНА С numpy. Тени НЕ подняты."
  echo "  проверь:  source .venv/bin/activate && python3 -c 'import numpy'"
  exit 1
fi
echo "питон: $PY"

zapustit () {
  IMYA="$1"; shift
  PID="research_lab/data/ten_${IMYA}.pid"
  if [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then
    echo "  ${IMYA}: уже работает, процесс $(cat "$PID")"
    return
  fi
  nohup caffeinate -i "$PY" -u research_lab/ten.py "$@" \
      --minut 100000 --pauza 3600 >> "research_lab/data/ten_${IMYA}.log" 2>&1 &
  echo "  ${IMYA}: запущена, процесс $!"
}

echo "ПОДНИМАЮ ТЕНИ  $(date '+%Y-%m-%d %H:%M')"
ETS2_TREND_TF=1440 ETS2_WAVE_TF=240 ETS2_ENTRY_TF=60 ETS2_RISK_TF=240 \
zapustit ETS2S elder_triple_screen_v2 ElderTripleScreenV2Strategy ETS2S \
  --storona short --otstup 0.002 --zhdat 6 --stop 4 --hold 336 --porog 550

# 27.10: ETS2S2 — та же замороженная ETS2S, но одна позиция на монету СКВОЗЬ проходы (--blok-zhurnal).
# Старая ETS2S не трогается (78 % её решений наложены — ETS2S_POVTOR_ITOG_2026_10_27.md); сравниваем обе.
ETS2_TREND_TF=1440 ETS2_WAVE_TF=240 ETS2_ENTRY_TF=60 ETS2_RISK_TF=240 \
zapustit ETS2S2 elder_triple_screen_v2 ElderTripleScreenV2Strategy ETS2S2 \
  --storona short --otstup 0.002 --zhdat 6 --stop 4 --hold 336 --porog 550 --blok-zhurnal

# ТРИ ВЫХОДА НА ОДНОМ СИГНАЛЕ. Вход и стоп те же, что у ETS2S; пишутся
# три журнала: ten_ETS2X.jsonl (CONTROL), _24H и _WIDE. Действующая тень
# ETS2S этим не затрагивается и остаётся замороженным контролем.
# Правила и ворота: research_lab/PREREG_TRI_TENI_2026_09_15.md
# ETS2X ОТКЛЮЧЁН 15 сентября, в день запуска, до единой записи в журнал.
# Причина показана демонстрацией, а не рассуждением: варианты выхода
# считались в момент закрытия КОНТРОЛЬНОЙ сделки, и sim_limit, не дождавшись
# своей цели, закрывала их по последнему доступному бару. На синтетике
# WIDE вернула РОВНО ТОТ ЖЕ R, что и CONTROL (+0.1427), то есть становилась
# копией контроля именно там, где обязана отличаться — на медленных
# победителях. Ветка не имеет права умирать оттого, что умерла соседняя.
#
# Правильное устройство — не ещё одно условие здесь, а отдельное ядро:
# неизменяемый журнал входов, независимые движки выхода со своим сроком
# жизни, парный оценщик по одной когорте. research_lab/yadro.py.
#
# ETS2_TREND_TF=1440 ETS2_WAVE_TF=240 ETS2_ENTRY_TF=60 ETS2_RISK_TF=240 \
# zapustit ETS2X elder_triple_screen_v2 ElderTripleScreenV2Strategy ETS2X \
#   --storona short --otstup 0.002 --zhdat 6 --stop 4 --hold 336 \
#   --porog 900 --varianty

zapustit ATT1 alt_trendline_touch_v1 AltTrendlineTouchV1Strategy ATT1 \
  --vhod rynok --storona short --stop 6 --hold 336 --rezhim "флет-" \
  --kuldaun 8 --porog 400

echo "готово. Проверить:  python3 research_lab/svodka.py"
