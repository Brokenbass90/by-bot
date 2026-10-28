# Разбор сделок под лупой (автоматически, `razbor_sdelok.py`) — H1 в кэше по 17.10

Типы убытков: **VHOD_RANO** — памп ещё не выдохся (против нас ≥ 1R / ≥ 15 % в первые 6 ч) → чинить ВХОД (ждать истощения);
**OTDALI_PRIBYL** — был плюс ≥ 1R / ≥ 10 %, закрыли хуже → чинить ВЫХОД; **MEDLENNYY** — без резких движений → слабый сигнал.

- PUMP4: HOROSHAYA 32, MEDLENNYY 17
- SHORT_HVOST: HOROSHAYA 9, MEDLENNYY 7

| нога | монета | дата | итог | тип | против нас (макс) | в нашу сторону (макс) | рост 24 ч до входа % | режим BTC | разброс альтов | график |
|---|---|---|---|---|---|---|---|---|---|---|
| PUMP4 | PEOPLEUSDT | 2026-09-18 | -1.01 | MEDLENNYY | 1.02 | 0.11 | 2.4 | NEUTRAL | 0.0376 | razbor/PUMP4_PEOPLEUSDT_2026-09-18.png |
| PUMP4 | APTUSDT | 2026-09-20 | -1.01 | MEDLENNYY | 1.03 | 0.16 | -2.0 | BULL_TREND | 0.1123 | razbor/PUMP4_APTUSDT_2026-09-20.png |
| PUMP4 | ALLOUSDT | 2026-09-22 | -1.01 | MEDLENNYY | 1.07 | 0.18 | -4.7 | BULL_TREND | 0.057 | razbor/PUMP4_ALLOUSDT_2026-09-22.png |
| PUMP4 | OPUSDT | 2026-09-19 | -1.01 | MEDLENNYY | 1.01 | 0.18 | 3.9 | BULL_TREND | 0.1256 | razbor/PUMP4_OPUSDT_2026-09-19.png |
| PUMP4 | AAVEUSDT | 2026-09-30 | -1.01 | MEDLENNYY | 1.01 | 0.07 | -6.2 | NEUTRAL | 0.0502 | razbor/PUMP4_AAVEUSDT_2026-09-30.png |
| PUMP4 | BROCCOLIUSDT | 2026-09-22 | -1.01 | MEDLENNYY | 1.02 | 0.04 | 9.0 | BULL_TREND | 0.057 | razbor/PUMP4_BROCCOLIUSDT_2026-09-22.png |
| PUMP4 | TUTUSDT | 2026-09-16 | -1.01 | MEDLENNYY | 1.02 | 0.02 | -0.4 | BEAR_TREND | 0.0873 | razbor/PUMP4_TUTUSDT_2026-09-16.png |
| PUMP4 | MMTUSDT | 2026-09-19 | -0.54 | MEDLENNYY | 0.71 | 0.09 | 9.1 | BULL_TREND | 0.1256 | razbor/PUMP4_MMTUSDT_2026-09-19.png |
| PUMP4 | COAIUSDT | 2026-10-04 | +0.35 | HOROSHAYA | 0.04 | 0.59 | 4.6 | NEUTRAL | 0.0496 | razbor/PUMP4_COAIUSDT_2026-10-04.png |
| PUMP4 | NILUSDT | 2026-10-01 | +0.35 | HOROSHAYA | 0.12 | 0.45 | -1.7 | BULL_TREND | 0.0356 | razbor/PUMP4_NILUSDT_2026-10-01.png |
| PUMP4 | INJUSDT | 2026-10-14 | +0.35 | HOROSHAYA | 0.05 | 0.47 | 1.2 | NEUTRAL | 0.0428 | razbor/PUMP4_INJUSDT_2026-10-14.png |
| PUMP4 | NILUSDT | 2026-10-11 | +0.35 | HOROSHAYA | 0.18 | 0.58 | 5.5 | NEUTRAL | 0.0553 | razbor/PUMP4_NILUSDT_2026-10-11.png |
| SHORT_HVOST | BICOUSDT | 2026-09-07 | -4.73 | MEDLENNYY | 3.91 | 3.3 | None | NEUTRAL | 0.053 | razbor/SHORT_HVOST_BICOUSDT_2026-09-07.png |
| SHORT_HVOST | BICOUSDT | 2026-09-16 | -3.88 | MEDLENNYY | 5.91 | 0.09 | -4.4 | BEAR_TREND | 0.0873 | razbor/SHORT_HVOST_BICOUSDT_2026-09-16.png |
| SHORT_HVOST | BICOUSDT | 2026-09-08 | -3.74 | MEDLENNYY | 9.02 | 1.33 | 1.4 | NEUTRAL | 0.0491 | razbor/SHORT_HVOST_BICOUSDT_2026-09-08.png |
| SHORT_HVOST | BICOUSDT | 2026-09-17 | -2.74 | MEDLENNYY | 2.92 | 0.68 | 2.6 | BEAR_TREND | 0.0462 | razbor/SHORT_HVOST_BICOUSDT_2026-09-17.png |
| SHORT_HVOST | BICOUSDT | 2026-10-02 | -1.95 | MEDLENNYY | 3.13 | 6.75 | 1.8 | BULL_TREND | 0.0336 | razbor/SHORT_HVOST_BICOUSDT_2026-10-02.png |
| SHORT_HVOST | BICOUSDT | 2026-10-01 | -0.97 | MEDLENNYY | 1.18 | 3.97 | 3.5 | BULL_TREND | 0.0356 | razbor/SHORT_HVOST_BICOUSDT_2026-10-01.png |
| SHORT_HVOST | BICOUSDT | 2026-09-14 | -0.68 | MEDLENNYY | 2.6 | 1.97 | -2.2 | NEUTRAL | 0.0552 | razbor/SHORT_HVOST_BICOUSDT_2026-09-14.png |
| SHORT_HVOST | BICOUSDT | 2026-09-13 | +0.70 | HOROSHAYA | 1.49 | 3.39 | -4.4 | NEUTRAL | 0.0335 | razbor/SHORT_HVOST_BICOUSDT_2026-09-13.png |
| SHORT_HVOST | BICOUSDT | 2026-09-09 | +3.82 | HOROSHAYA | 2.8 | 5.49 | 2.2 | NEUTRAL | 0.0518 | razbor/SHORT_HVOST_BICOUSDT_2026-09-09.png |
| SHORT_HVOST | BICOUSDT | 2026-09-09 | +6.54 | HOROSHAYA | 1.25 | 15.67 | -4.8 | NEUTRAL | 0.0518 | razbor/SHORT_HVOST_BICOUSDT_2026-09-09.png |
| SHORT_HVOST | AKEUSDT | 2026-09-21 | +12.39 | HOROSHAYA | 1.78 | 47.29 | -8.2 | NEUTRAL | 0.0659 | razbor/SHORT_HVOST_AKEUSDT_2026-09-21.png |
| SHORT_HVOST | LUMIAUSDT | 2026-10-11 | +12.65 | HOROSHAYA | 2.15 | 18.92 | 25.3 | NEUTRAL | 0.0553 | razbor/SHORT_HVOST_LUMIAUSDT_2026-10-11.png |

Чего не хватает для полного разбора (инструменты): стакан/глубина в момент входа по монете; OI и ликвидации по часам; фандинг по часам;
спот против перпа (кто толкает памп); новости/листинги по монете; данные после 17.10 в кэше (обновить H1 на Mac).
