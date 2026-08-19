#!/bin/bash
# НОЧЬ: контроль случайным входом по всем ногам с ШИРОКИМ стопом.
#
# Прошлый ночной прогон гонял ×6 в шорт и ×4 в лонг, но многие ноги
# настроены на очень узкий стоп (HZBO1 sl_atr_mult=0.50, у ACB1 и ARS1
# плечо 93). Для них ×6 всё равно оставляет плечо выше 20, и издержки
# съедают сигнал раньше, чем мы его увидим.
#
# Здесь стоп ×12 — чтобы у самых узких ног плечо упало до нормального,
# и стало видно, есть ли под издержками сигнал вообще.
# Значение объявлено ДО прогона и не подбирается.
#
# Запускать: nohup ./research_lab/queue_stops.sh &
cd "$(dirname "$0")/.."
L=research_lab/controls_wide.log
: > $L
TO=""
command -v timeout  >/dev/null 2>&1 && TO="timeout 2400"
command -v gtimeout >/dev/null 2>&1 && TO="gtimeout 2400"
go () {
  echo "=== $(date -u +%F\ %H:%M) $3 $4 x$5 $7" >> $L
  nice -n 15 $TO python3 research_lab/random_control.py \
     "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" 2>&1 | grep -v "^\.\.\." >> $L
}
go alt_bear_regime_continuation_v1 AltBearRegimeContinuationV1Strategy BRC1 short 12.0 336 "флет-" 0
go alt_bear_regime_continuation_v1 AltBearRegimeContinuationV1Strategy BRC1 long  12.0 336 "флет+" 0
go alt_channel_bounce_v1 AltChannelBounceV1Strategy ACB1 short 12.0 336 "флет-" 0
go alt_channel_bounce_v1 AltChannelBounceV1Strategy ACB1 long  12.0 336 "флет+" 0
go alt_elder_revived_v1 AltElderRevivedV1 ELDERREV short 12.0 336 "флет-" 6
go alt_elder_revived_v1 AltElderRevivedV1 ELDERREV long  12.0 336 "флет+" 6
go alt_horizontal_break_v1 AltHorizontalBreakV1Strategy HZBO1 short 12.0 336 "флет-" 5
go alt_horizontal_break_v1 AltHorizontalBreakV1Strategy HZBO1 long  12.0 336 "флет+" 5
go alt_range_reclaim_v1 AltRangeReclaimV1Strategy ARR1 short 12.0 336 "флет-" 6
go alt_range_reclaim_v1 AltRangeReclaimV1Strategy ARR1 long  12.0 336 "флет+" 6
go alt_range_scalp_v1 AltRangeScalpV1Strategy ARS1 short 12.0 336 "флет-" 4
go alt_range_scalp_v1 AltRangeScalpV1Strategy ARS1 long  12.0 336 "флет+" 4
go alt_resistance_fade_v1 AltResistanceFadeV1Strategy ARF1 short 12.0 336 "флет-" 4
go alt_resistance_fade_v1 AltResistanceFadeV1Strategy ARF1 long  12.0 336 "флет+" 4
go alt_resistance_fade_v2 AltResistanceFadeV2Strategy ARF2 short 12.0 336 "флет-" 3
go alt_resistance_fade_v2 AltResistanceFadeV2Strategy ARF2 long  12.0 336 "флет+" 3
go alt_sloped_channel_v1 AltSlopedChannelV1Strategy ASC1 short 12.0 336 "флет-" 6
go alt_sloped_channel_v1 AltSlopedChannelV1Strategy ASC1 long  12.0 336 "флет+" 6
go alt_sloped_momentum_v1 AltSlopedMomentumV1Strategy ASM1 short 12.0 336 "флет-" 6
go alt_sloped_momentum_v1 AltSlopedMomentumV1Strategy ASM1 long  12.0 336 "флет+" 6
go alt_support_bounce_v2 AltSupportBounceV2Strategy ASB2 short 12.0 336 "флет-" 0
go alt_support_bounce_v2 AltSupportBounceV2Strategy ASB2 long  12.0 336 "флет+" 0
go alt_support_reclaim_v1 AltSupportReclaimV1Strategy ASR1 short 12.0 336 "флет-" 6
go alt_support_reclaim_v1 AltSupportReclaimV1Strategy ASR1 long  12.0 336 "флет+" 6
go alt_trendline_touch_v1 AltTrendlineTouchV1Strategy ATT1 short 12.0 336 "флет-" 8
go alt_trendline_touch_v1 AltTrendlineTouchV1Strategy ATT1 long  12.0 336 "флет+" 8
go alt_trendline_touch_v2 AltTrendlineTouchV2Strategy ATT2 short 12.0 336 "флет-" 8
go alt_trendline_touch_v2 AltTrendlineTouchV2Strategy ATT2 long  12.0 336 "флет+" 8
go alt_volume_spike_momentum_v1 AltVolumeSpikeV1Strategy VSM1 short 12.0 336 "флет-" 0
go alt_volume_spike_momentum_v1 AltVolumeSpikeV1Strategy VSM1 long  12.0 336 "флет+" 0
go btc_cycle_continuation_v1 BTCCycleContinuationV1Strategy BTCC2 short 12.0 336 "флет-" 8
go btc_cycle_continuation_v1 BTCCycleContinuationV1Strategy BTCC2 long  12.0 336 "флет+" 8
go btc_cycle_level_target_v2 BTCCycleLevelTargetV2Strategy BTCL2 short 12.0 336 "флет-" 8
go btc_cycle_level_target_v2 BTCCycleLevelTargetV2Strategy BTCL2 long  12.0 336 "флет+" 8
go btc_cycle_pullback_v1 BTCCyclePullbackV1Strategy BTCC1 short 12.0 336 "флет-" 8
go btc_cycle_pullback_v1 BTCCyclePullbackV1Strategy BTCC1 long  12.0 336 "флет+" 8
go btc_eth_midterm_pullback BTCETHMidtermPullbackStrategy MTPB short 12.0 336 "флет-" 7
go btc_eth_midterm_pullback BTCETHMidtermPullbackStrategy MTPB long  12.0 336 "флет+" 7
go btc_eth_midterm_pullback_v2 BTCETHMidtermPullbackV2Strategy MTPB2 short 12.0 336 "флет-" 5
go btc_eth_midterm_pullback_v2 BTCETHMidtermPullbackV2Strategy MTPB2 long  12.0 336 "флет+" 5
go btc_eth_midterm_short_v1 BTCETHMidtermShortV1Strategy MTSV1 short 12.0 336 "флет-" 12
go btc_eth_midterm_short_v1 BTCETHMidtermShortV1Strategy MTSV1 long  12.0 336 "флет+" 12
go btc_eth_midterm_short_v2 BTCETHMidtermShortV2Strategy MTSV2 short 12.0 336 "флет-" 12
go btc_eth_midterm_short_v2 BTCETHMidtermShortV2Strategy MTSV2 long  12.0 336 "флет+" 12
go btc_eth_midterm_v3 BTCETHMidtermV3Strategy MTPB3 short 12.0 336 "флет-" 0
go btc_eth_midterm_v3 BTCETHMidtermV3Strategy MTPB3 long  12.0 336 "флет+" 0
go btc_regime_flip_continuation_v1 BTCRegimeFlipContinuationV1Strategy BTCRF1 short 12.0 336 "флет-" 8
go btc_regime_flip_continuation_v1 BTCRegimeFlipContinuationV1Strategy BTCRF1 long  12.0 336 "флет+" 8
go btc_regime_retest_v1 BTCRegimeRetestV1Strategy BTCR1 short 12.0 336 "флет-" 4
go btc_regime_retest_v1 BTCRegimeRetestV1Strategy BTCR1 long  12.0 336 "флет+" 4
go btc_sloped_reclaim_v1 BTCSlopedReclaimV1Strategy BTCS1 short 12.0 336 "флет-" 8
go btc_sloped_reclaim_v1 BTCSlopedReclaimV1Strategy BTCS1 long  12.0 336 "флет+" 8
go elder_crypto_v1 ElderCryptoV1Strategy ECV1 short 12.0 336 "флет-" 4
go elder_crypto_v1 ElderCryptoV1Strategy ECV1 long  12.0 336 "флет+" 4
go elder_triple_screen_v2 ElderTripleScreenV2Strategy ETS2 short 12.0 336 "флет-" 3
go elder_triple_screen_v2 ElderTripleScreenV2Strategy ETS2 long  12.0 336 "флет+" 3
go elder_triple_screen_v3 ElderTripleScreenV3Strategy ETS3 short 12.0 336 "флет-" 4
go elder_triple_screen_v3 ElderTripleScreenV3Strategy ETS3 long  12.0 336 "флет+" 4
go funding_rate_reversion_v1 FundingRateReversionV1 FR short 12.0 336 "флет-" 0
go funding_rate_reversion_v1 FundingRateReversionV1 FR long  12.0 336 "флет+" 0
go grid_smart_v1 GridSmartV1Strategy GS1 short 12.0 336 "флет-" 0
go grid_smart_v1 GridSmartV1Strategy GS1 long  12.0 336 "флет+" 0
go impulse_volume_breakout_v1 ImpulseVolumeBreakoutV1Strategy IVB1 short 12.0 336 "флет-" 1
go impulse_volume_breakout_v1 ImpulseVolumeBreakoutV1Strategy IVB1 long  12.0 336 "флет+" 1
go inplay_retest_v3 InplayRetestV3Strategy IRV3 short 12.0 336 "флет-" 0
go inplay_retest_v3 InplayRetestV3Strategy IRV3 long  12.0 336 "флет+" 0
go inplay_retest_v4 InplayRetestV4Strategy IRV4 short 12.0 336 "флет-" 0
go inplay_retest_v4 InplayRetestV4Strategy IRV4 long  12.0 336 "флет+" 0
go liquidation_cascade_entry_v1 LiquidationCascadeEntryV1 LC short 12.0 336 "флет-" 0
go liquidation_cascade_entry_v1 LiquidationCascadeEntryV1 LC long  12.0 336 "флет+" 0
go micro_scalper_breakout_v1 MicroScalperBreakoutV1Strategy MSBRK short 12.0 336 "флет-" 0
go micro_scalper_breakout_v1 MicroScalperBreakoutV1Strategy MSBRK long  12.0 336 "флет+" 0
go micro_scalper_v1 MicroScalperV1Strategy MSCALP short 12.0 336 "флет-" 0
go micro_scalper_v1 MicroScalperV1Strategy MSCALP long  12.0 336 "флет+" 0
go pump_fade_smart_v1 PumpFadeSmartV1Strategy PFS1 short 12.0 336 "флет-" 4
go pump_fade_smart_v1 PumpFadeSmartV1Strategy PFS1 long  12.0 336 "флет+" 4
go pump_fade_v2 PumpFadeV2Strategy PF2 short 12.0 336 "флет-" 0
go pump_fade_v2 PumpFadeV2Strategy PF2 long  12.0 336 "флет+" 0
go pump_fade_v4r PumpFadeV4RStrategy PF short 12.0 336 "флет-" 0
go pump_fade_v4r PumpFadeV4RStrategy PF long  12.0 336 "флет+" 0
go pump_momentum_v1 PumpMomentumV1Strategy PM short 12.0 336 "флет-" 0
go pump_momentum_v1 PumpMomentumV1Strategy PM long  12.0 336 "флет+" 0
go scalper_bounce_v2 ScalperBounceV2Strategy SB2 short 12.0 336 "флет-" 2
go scalper_bounce_v2 ScalperBounceV2Strategy SB2 long  12.0 336 "флет+" 2
go scalper_breakout_v2 ScalperBreakoutV2Strategy SBR2 short 12.0 336 "флет-" 4
go scalper_breakout_v2 ScalperBreakoutV2Strategy SBR2 long  12.0 336 "флет+" 4
go scalper_classic_v1 ScalperClassicV1Strategy SC1 short 12.0 336 "флет-" 1
go scalper_classic_v1 ScalperClassicV1Strategy SC1 long  12.0 336 "флет+" 1
go scalper_sweep_v2 ScalperSweepV2Strategy SS2 short 12.0 336 "флет-" 3
go scalper_sweep_v2 ScalperSweepV2Strategy SS2 long  12.0 336 "флет+" 3
go sloped_break_retest_v1 SlopedBreakRetestV1Strategy SBR1 short 12.0 336 "флет-" 0
go sloped_break_retest_v1 SlopedBreakRetestV1Strategy SBR1 long  12.0 336 "флет+" 0
go sloped_break_retest_v2 SlopedBreakRetestV2Strategy SLBR2 short 12.0 336 "флет-" 0
go sloped_break_retest_v2 SlopedBreakRetestV2Strategy SLBR2 long  12.0 336 "флет+" 0
go sloped_resistance_choch_v1 SlopedResistanceChochV1Strategy SRC1 short 12.0 336 "флет-" 0
go sloped_resistance_choch_v1 SlopedResistanceChochV1Strategy SRC1 long  12.0 336 "флет+" 0
go smart_grid SmartGridStrategy SG short 12.0 336 "флет-" 0
go smart_grid SmartGridStrategy SG long  12.0 336 "флет+" 0
echo "=== $(date -u +%F\ %H:%M) встречные ноги" >> $L
nice -n 15 python3 research_lab/antileg.py >> $L 2>&1
echo "=== НОЧЬ ЗАВЕРШЕНА $(date -u)" >> $L
