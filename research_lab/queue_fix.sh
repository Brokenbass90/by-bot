#!/bin/bash
# ПЕРЕПРОГОН после исправления двойного исполнения первой цели. Собрана автоматически: research_lab/make_queue_all.py
#
# Пауза между сделками поделена на 12 — штатное значение задано
# в пятиминутках, а счётчик тикает раз в вызов.
# Порог различимости в машине теперь считается по фактическому
# разбросу конфигурации, а не по константе 1.03R.
#
# Запускать: nohup ./research_lab/queue_all.sh &
cd "$(dirname "$0")/.."
L=research_lab/queue_fix.log
: > $L
# timeout есть не везде: на macOS он приходит с coreutils как gtimeout.
# Если нет ни того ни другого — работаем без ограничения по времени.
TO=""
command -v timeout  >/dev/null 2>&1 && TO="timeout 3600"
command -v gtimeout >/dev/null 2>&1 && TO="gtimeout 3600"
run () {
  echo "=== $(date -u +%F\ %H:%M) старт $4 (пауза $5)" >> $L
  nice -n 15 $TO python3 research_lab/research_machine.py \
      --strategy "$1" --cls "$2" --prefix "$3" \
      --data research_lab/data/h1 --tag "$4" --root . --cooldown "$5" \
      > "research_lab/rm_$4.log" 2>&1
  echo "=== $(date -u +%F\ %H:%M) готово $4" >> $L
  sed -n '/ОТСЕВ/,$p' "research_lab/rm_$4.log" >> $L
}
run alt_elder_revived_v1               AltElderRevivedV1                    ELDERREV elderrev 6
run alt_horizontal_break_v1            AltHorizontalBreakV1Strategy         HZBO1   hzbo1    5
run alt_sloped_momentum_v1             AltSlopedMomentumV1Strategy          ASM1    asm1     6
run alt_volume_spike_momentum_v1       AltVolumeSpikeV1Strategy             VSM1    vsm1     0
run btc_cycle_continuation_v1          BTCCycleContinuationV1Strategy       BTCC2   btcc2    8
run btc_cycle_level_target_v2          BTCCycleLevelTargetV2Strategy        BTCL2   btcl2    8
run btc_cycle_pullback_v1              BTCCyclePullbackV1Strategy           BTCC1   btcc1    8
run btc_eth_midterm_pullback           BTCETHMidtermPullbackStrategy        MTPB    mtpb     7
run btc_eth_midterm_pullback_v2        BTCETHMidtermPullbackV2Strategy      MTPB2   mtpb2    5
run btc_eth_midterm_short_v1           BTCETHMidtermShortV1Strategy         MTSV1   mtsv1    12
run btc_eth_midterm_short_v2           BTCETHMidtermShortV2Strategy         MTSV2   mtsv2    12
run btc_eth_midterm_v3                 BTCETHMidtermV3Strategy              MTPB3   mtpb3    0
run btc_regime_retest_v1               BTCRegimeRetestV1Strategy            BTCR1   btcr1    4
run btc_sloped_reclaim_v1              BTCSlopedReclaimV1Strategy           BTCS1   btcs1    8
run elder_crypto_v1                    ElderCryptoV1Strategy                ECV1    ecv1     4
run elder_triple_screen_v2             ElderTripleScreenV2Strategy          ETS2    ets2     3
run elder_triple_screen_v3             ElderTripleScreenV3Strategy          ETS3    ets3     4
run impulse_volume_breakout_v1         ImpulseVolumeBreakoutV1Strategy      IVB1    ivb1     1
run inplay_retest_v4                   InplayRetestV4Strategy               IRV4    irv4     0
run scalper_bounce_v2                  ScalperBounceV2Strategy              SB2     sb2      2
run scalper_breakout_v2                ScalperBreakoutV2Strategy            SBR2    sbr2     4
run scalper_sweep_v2                   ScalperSweepV2Strategy               SS2     ss2      3
run sloped_break_retest_v1             SlopedBreakRetestV1Strategy          SBR1    sbr1     0
run sloped_resistance_choch_v1         SlopedResistanceChochV1Strategy      SRC1    src1     0
echo "=== ПЕРЕПРОГОН ЗАВЕРШЁН $(date -u)" >> $L
