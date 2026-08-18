#!/bin/bash
# ПОЛНАЯ ОЧЕРЕДЬ. Собрана автоматически: research_lab/make_queue_all.py
#
# Пауза между сделками поделена на 12 — штатное значение задано
# в пятиминутках, а счётчик тикает раз в вызов.
# Порог различимости в машине теперь считается по фактическому
# разбросу конфигурации, а не по константе 1.03R.
#
# Запускать: nohup ./research_lab/queue_all.sh &
cd "$(dirname "$0")/.."
L=research_lab/queue_all.log
: > $L
run () {
  echo "=== $(date -u +%F\ %H:%M) старт $4 (пауза $5)" >> $L
  nice -n 15 timeout 3600 python3 research_lab/research_machine.py \
      --strategy "$1" --cls "$2" --prefix "$3" \
      --data research_lab/data/h1 --tag "$4" --root . --cooldown "$5" \
      > "research_lab/rm_$4.log" 2>&1
  echo "=== $(date -u +%F\ %H:%M) готово $4" >> $L
  sed -n '/ОТСЕВ/,$p' "research_lab/rm_$4.log" >> $L
}
run alt_bear_regime_continuation_v1    AltBearRegimeContinuationV1Strategy  BRC1    brc1     0
run alt_channel_bounce_v1              AltChannelBounceV1Strategy           ACB1    acb1     0
run alt_elder_revived_v1               AltElderRevivedV1                    ELDERREV elderrev 6
run alt_horizontal_break_v1            AltHorizontalBreakV1Strategy         HZBO1   hzbo1    5
run alt_range_reclaim_v1               AltRangeReclaimV1Strategy            ARR1    arr1     6
run alt_range_scalp_v1                 AltRangeScalpV1Strategy              ARS1    ars1     4
run alt_resistance_fade_v1             AltResistanceFadeV1Strategy          ARF1    arf1     4
run alt_resistance_fade_v2             AltResistanceFadeV2Strategy          ARF2    arf2     3
run alt_sloped_channel_v1              AltSlopedChannelV1Strategy           ASC1    asc1     6
run alt_sloped_momentum_v1             AltSlopedMomentumV1Strategy          ASM1    asm1     6
run alt_support_bounce_v2              AltSupportBounceV2Strategy           ASB2    asb2     0
run alt_support_reclaim_v1             AltSupportReclaimV1Strategy          ASR1    asr1     6
run alt_trendline_touch_v1             AltTrendlineTouchV1Strategy          ATT1    att1     8
run alt_trendline_touch_v2             AltTrendlineTouchV2Strategy          ATT2    att2     8
run alt_volume_spike_momentum_v1       AltVolumeSpikeV1Strategy             VSM1    vsm1     0
run btc_cycle_continuation_v1          BTCCycleContinuationV1Strategy       BTCC2   btcc2    8
run btc_cycle_level_target_v2          BTCCycleLevelTargetV2Strategy        BTCL2   btcl2    8
run btc_cycle_pullback_v1              BTCCyclePullbackV1Strategy           BTCC1   btcc1    8
run btc_eth_midterm_pullback           BTCETHMidtermPullbackStrategy        MTPB    mtpb     7
run btc_eth_midterm_pullback_v2        BTCETHMidtermPullbackV2Strategy      MTPB2   mtpb2    5
run btc_eth_midterm_short_v1           BTCETHMidtermShortV1Strategy         MTSV1   mtsv1    12
run btc_eth_midterm_short_v2           BTCETHMidtermShortV2Strategy         MTSV2   mtsv2    12
run btc_eth_midterm_v3                 BTCETHMidtermV3Strategy              MTPB3   mtpb3    0
run btc_regime_flip_continuation_v1    BTCRegimeFlipContinuationV1Strategy  BTCRF1  btcrf1   8
run btc_regime_retest_v1               BTCRegimeRetestV1Strategy            BTCR1   btcr1    4
run btc_sloped_reclaim_v1              BTCSlopedReclaimV1Strategy           BTCS1   btcs1    8
run elder_crypto_v1                    ElderCryptoV1Strategy                ECV1    ecv1     4
run elder_triple_screen_v2             ElderTripleScreenV2Strategy          ETS2    ets2     3
run elder_triple_screen_v3             ElderTripleScreenV3Strategy          ETS3    ets3     4
run funding_rate_reversion_v1          FundingRateReversionV1               FR      fr       0
run grid_smart_v1                      GridSmartV1Strategy                  GS1     gs1      0
run impulse_volume_breakout_v1         ImpulseVolumeBreakoutV1Strategy      IVB1    ivb1     1
run inplay_retest_v3                   InplayRetestV3Strategy               IRV3    irv3     0
run inplay_retest_v4                   InplayRetestV4Strategy               IRV4    irv4     0
run liquidation_cascade_entry_v1       LiquidationCascadeEntryV1            LC      lc       0
run micro_scalper_breakout_v1          MicroScalperBreakoutV1Strategy       MSBRK   msbrk    0
run micro_scalper_v1                   MicroScalperV1Strategy               MSCALP  mscalp   0
run pump_fade_smart_v1                 PumpFadeSmartV1Strategy              PFS1    pfs1     4
run pump_fade_v2                       PumpFadeV2Strategy                   PF2     pf2      0
run pump_fade_v4r                      PumpFadeV4RStrategy                  PF      pf       0
run pump_momentum_v1                   PumpMomentumV1Strategy               PM      pm       0
run scalper_bounce_v2                  ScalperBounceV2Strategy              SB2     sb2      2
run scalper_breakout_v2                ScalperBreakoutV2Strategy            SBR2    sbr2     4
run scalper_classic_v1                 ScalperClassicV1Strategy             SC1     sc1      1
run scalper_sweep_v2                   ScalperSweepV2Strategy               SS2     ss2      3
run sloped_break_retest_v1             SlopedBreakRetestV1Strategy          SBR1    sbr1     0
run sloped_break_retest_v2             SlopedBreakRetestV2Strategy          SLBR2   slbr2    0
run sloped_resistance_choch_v1         SlopedResistanceChochV1Strategy      SRC1    src1     0
run smart_grid                         SmartGridStrategy                    SG      sg       0
echo "=== ПОЛНАЯ ОЧЕРЕДЬ ЗАВЕРШЕНА $(date -u)" >> $L
