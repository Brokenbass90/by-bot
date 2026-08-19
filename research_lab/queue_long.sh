#!/bin/bash
# Очередь: кандидаты на ДЛИННУЮ сторону под будущий бычий рынок.
# Запускать на машине владельца: nohup ./research_lab/queue_long.sh &
cd "$(dirname "$0")/.."
L=research_lab/queue_long.log
run () {
  echo "=== $(date -u +%F\ %H:%M) старт $4" >> $L
  nice -n 15 python3 research_lab/research_machine.py \
      --strategy "$1" --cls "$2" --prefix "$3" \
      --data research_lab/data/h1 --tag "$4" --root . \
      > "research_lab/rm_$4.log" 2>&1
  echo "=== $(date -u +%F\ %H:%M) готово $4" >> $L
  sed -n '/ОТСЕВ/,$p' "research_lab/rm_$4.log" >> $L
}
run alt_support_reclaim_v1     AltSupportReclaimV1Strategy     ASR1  asr1
run impulse_volume_breakout_v1 ImpulseVolumeBreakoutV1Strategy IVB1  ivb1
run alt_sloped_channel_v1      AltSlopedChannelV1Strategy      ASC1  asc1
run alt_horizontal_break_v1    AltHorizontalBreakV1Strategy    HZBO1 hzbo1
echo "=== ОЧЕРЕДЬ ЛОНГ ЗАВЕРШЕНА $(date -u)" >> $L
