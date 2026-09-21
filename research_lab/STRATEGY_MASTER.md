# STRATEGY_MASTER — вид на реестр

Сгенерировано 2026-09-21 10:50 UTC из `research_lab/data/reestr.json` (единственная машинная база) и `research_lab/fabrika/verdikty.jsonl` (журнал доказательств).
Руками не править: `python3 research_lab/fabrika/master.py`. Приоритеты — в `ROADMAP.md`.

## Слоты портфеля

Слот — это место в портфеле, а не обещанный победитель. Умерла нога — слот ищет другую.

**Акции**

| id | состояние | главное | следующий шаг | владелец |
|---|---|---|---|---|
| ALPACA_INTENDED | READY_FOR_BUILD | 14.48% годовых, DD 7.57%, PF 1.81 — история | PAPER 0/7 → 7/7 → dossier → tiny-live по решению владельца | Codex |

**Крипта: падение / флет вниз**

| id | состояние | главное | следующий шаг | владелец |
|---|---|---|---|---|
| ATT1_AGG | SHADOW | +0.055R к контролю режима при sigma 0.27; по деньгам -10.2R | 1300 решений → canary (Codex) | Codex |

**Крипта: нейтральный / боковик**

| id | состояние | главное | следующий шаг | владелец |
|---|---|---|---|---|
| XSEC_V3_TEN | SHADOW | тень 57 дн: +$88.9 валовых на $1000, половины +45.6/+43.3, t≈0.35; PIT-упрощённый в фабри… | XSEC_EXACT_TARGET_WEIGHTS_PIT | Codex (тень) / Claude (PIT) |
| P_KR_XSEC_V3 | HYPOTHESIS | t=1.65 (порог 2.5) |  |  |

**Крипта: рост**

| id | состояние | главное | следующий шаг | владелец |
|---|---|---|---|---|
| SBR1_MAJOR8 | SHADOW | история 2023–25: 64 сделки +24.26R PF 2.06; reserved OOS 2025-10…07: 16 сделок −3.31R PF … | снять журнал тени с VPS и посчитать против контроля по PREREG_SBR1_SH… | Codex (VPS) / Claude (счёт) |

**Фоновые эксперименты**

| id | состояние | главное | следующий шаг | владелец |
|---|---|---|---|---|
| ETS2M | SHADOW | 388/900 входов; R до когорты не считается; темп сигналов упал с 18.09 | копить до 900 и терминальности всех движков | Claude |
| ETS2S | SHADOW | информация PASS: +0.0668R к контролю режима, 4.22σ на 2803; деньги −329.9R; избыток по по… | деньги или нет — отвечает ETS2M | Claude |

**Без слота**

| id | состояние | главное | следующий шаг | владелец |
|---|---|---|---|---|
| ARB_EVENT_CLASS | POSITIVE_LEAD | EGLD: 39.6-58.4 бп чистыми, жив в 100% срезов 11 суток | месяц следить за справочниками монет четырёх бирж и ловить КАЖДУЮ нов… |  |
| GOLD | POSITIVE_LEAD | Элдер на золоте 2019–22: +4.79R, 0.93σ (ЧАСТИЧНО); фабрика 21.09: 13 из 14 LOW_N на 2 год… | глубже история XAUUSD (мост MT5 / выгрузка) |  |

## Гипотезы без слота (ждут данных/переходника или «плюс без уверенности»)

- `KAPITULYACIYA__crypto137__long` — z=0.33 (порог 3.1), O3 +
- `KAPITULYACIYA__crypto137__short` — z=1.47 (порог 3.1), O3 +
- `KAPITULYACIYA__fx7__long` — O1: n=43
- `KAPITULYACIYA__fx7__short` — O1: n=37
- `KAPITULYACIYA__gold__long` — O1: n=5
- `KAPITULYACIYA__gold__short` — O1: n=4
- `MOMENTUM_30D__gold__long` — O1: n=11
- `MOMENTUM_30D__gold__short` — O1: n=10
- `NOCHNOY_RAZRYV` — НЕ ИЗМЕРЕН
- `OBEM_IMPULS__fx7__long` — O1: n=2
- `OBEM_IMPULS__fx7__short` — O1: n=4
- `OBEM_IMPULS__gold__long` — O1: n=0
- `OBEM_IMPULS__gold__short` — O1: n=0
- `OTKAT_V_TRENDE__gold__long` — O1: n=35
- `OTKAT_V_TRENDE__gold__short` — O1: n=11
- `PROBOY_55__gold__short` — O1: n=46
- `P_AKC_REVERSAL_5D` — t=0.38 (порог 2.5)
- `RAZBROS_RYNKA` — не измерен
- `SZHATIE_BB__crypto137__long` — z=0.86 (порог 3.1), O3 +
- `SZHATIE_BB__crypto137__short` — z=0.74 (порог 3.1), O3 нет
- `SZHATIE_BB__fx7__short` — z=0.97 (порог 3.1), окна O3 нет
- `SZHATIE_BB__gold__long` — O2: n=43
- `SZHATIE_BB__gold__short` — O2: n=39
- `VOZVRAT_K_SREDNEY__gold__long` — O1: n=33
- `VOZVRAT_K_SREDNEY__gold__short` — O1: n=34

## Доказательства по живым строкам

- `ALPACA_INTENDED`: research_lab/data/alpaca_namerennyy_ten.jsonl
- `ATT1_AGG`: research_lab/data/ten_ATT1.jsonl
- `ETS2M`: research_lab/data/yadro/ETS2M/
- `ETS2S`: research_lab/data/ten_ETS2S.jsonl
- `SBR1_MAJOR8`: research_lab/results/att1_sbr1_presealed_economics_diagnostic_20260823/receipt.json; bybit-bot-recovery-20260824/reports/ATT1_SBR1_RESERVED_OOS_RESULT_2026_08_…
- `XSEC_V3_TEN`: runtime/xsec_v3_shadow/ledger.jsonl; research_lab/fabrika/verdikty.jsonl#P_KR_XSEC_V3
- `ARB_EVENT_CLASS`: research_lab/data/arb_ten.jsonl, ITOG.md часть 67
- `GOLD`: ветка claude/alpaca-2026-09-07, коммиты 8 сентября

## Фабрика

Вердиктов всего: NEGATIVE 28, INCONCLUSIVE_LOW_N 21, PLUS_NO_CONFIDENCE 7, BLOCKED_DATA 2, BLOCKED_PARITY 1, PARITY_PASS 1

## Архив (NEGATIVE, 45)

Решений не принимает. Хранится, чтобы не убивать второй раз.

- breakout: PROBOY_55__crypto137__long, PROBOY_55__crypto137__short, PROBOY_55__fx7__long, PROBOY_55__fx7__short, PROBOY_55__gold__long
- flow_continuation: OBEM_IMPULS__crypto137__long, OBEM_IMPULS__crypto137__short
- funding_carry: P_KR_FANDING_KERRI
- high_proximity: P_AKC_BLIZ_MAX_126
- low_volatility: P_AKC_LOW_VOL_60
- mean_reversion: VOZVRAT_K_SREDNEY__crypto137__long, VOZVRAT_K_SREDNEY__crypto137__short, VOZVRAT_K_SREDNEY__fx7__long, VOZVRAT_K_SREDNEY__fx7__short
- sloped_retest: SBR1_LONG_TREND
- trend_pullback: OTKAT_V_TRENDE__crypto137__long, OTKAT_V_TRENDE__crypto137__short, OTKAT_V_TRENDE__fx7__long, OTKAT_V_TRENDE__fx7__short
- trendline_touch: ATT1_LONG_TREND, ATT1_SHORT_TREND
- ts_momentum: MOMENTUM_30D__crypto137__long, MOMENTUM_30D__crypto137__short, MOMENTUM_30D__fx7__long, MOMENTUM_30D__fx7__short
- volatility_expansion: SZHATIE_BB__fx7__long
- xs_momentum: P_AKC_MOM_6_1
- xs_momentum_long: P_AKC_MOM_6_1_LONG
- прочее: ALPACA_A_G2, ARB_EGLD, ATT1_FILTER, ATT1_KASANIE, BETA_BTC, CS_OBOROT, IMPULS_7D, OI_KVINTIL, OI_RASHOZHDENIE, OTKAT_KRIPTA, RAZMAH_NORM, RAZMAH_SVECHI, RAZVOROT_1D, SBR1_ISSLED, TELO_SVECHI, UROVNI_OTBOY, VOZRAST_MONETY
