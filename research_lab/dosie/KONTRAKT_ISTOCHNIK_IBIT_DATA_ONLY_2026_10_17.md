# Контракт для Codex: источник закрытия IBIT + BTC-референс, DATA-ONLY / ORDERS_OFF (Claude, 17.10.2026)

Для досье `DOSIE_ETF_PREMIYA_BTC_V1.md` (DRAFT). Можно строить параллельно с CONFIRM вперёд — ордеров нет, денег нет,
KITY/Alpaca/NET не трогать. Правило сигнала заморожено (PREREG_ETF_PREMIYA_2026_10_17) и в этом контракте не меняется.

## 1. Что нужно получать каждую сессию NYSE
| поле | источник (предложение) | требование |
|---|---|---|
| `ibit_close` | Alpaca market data, дневной бар IBIT (официальное закрытие сессии) | значение и **время получения** (`received_at`, UTC мс) |
| `ibit_close_src_ts` | метка бара/аукциона от источника | ≥ 16:00:00 ET этого дня, не позже |
| `btc_ref` | закрытие часового бара BTCUSDT [15:00,16:00) ET — Binance (как в DEV) и Bybit (исполнитель) | оба; расхождение > 0.2 % → флаг |
| `session` | календарь NYSE (Alpaca calendar) | праздники/сокращённые дни: закрытие 13:00 ET → ref-бар [12:00,13:00) ET |

## 2. Контроль качества (детерминированно)
1. **Свежесть:** `received_at − 16:00 ET` ≤ 30 мин → `FRESH`; ≤ 6 ч → `LATE` (сигнал пишется, исполнение NO_SEND);
   иначе `MISSING`.
2. **Сверка:** `ibit_close` vs Massive grouped (`data/akcii_grouped/<день>.json`, когда появится) — расхождение > 0.5 % → `DEFECT`.
3. **Без заглядывания:** нельзя использовать цену IBIT с меткой > 16:00 ET (after-hours), нельзя брать BTC позже ref-бара.
4. **Пропуски:** отсутствующая сессия не интерполируется; история z пересчитывается только по реально полученным сессиям.
5. **Рестарт:** идемпотентно по `session`; повторный запуск не создаёт второе решение; журнал append-only с sha строки.

## 3. Выход (одна строка на сессию, append-only)
`session, ibit_close, ibit_close_src_ts, received_at, btc_ref_binance, btc_ref_bybit, premiya, z, sobytie, znak,
freshness, sverka_massive, decided_at, rule_sha, source_sha` → файл/таблица, которую Claude сверяет с тенью
`data/etf_premiya/ten_ETF_PREMIYA.jsonl`: события и знаки 1:1, z ±0.01.

## 4. Приёмка (ORDERS_OFF PASS)
- 10 подряд сессий без `MISSING`/`DEFECT`, ≥ 80 % `FRESH`;
- 100 % совпадение событий/знаков с тенью Claude;
- тест рестарта и тест сокращённого дня (фикстуры);
- ни одного вызова ордерного API.
После этого досье получает статус READY_FOR_ORDERS_OFF; до CONFIRM вперёд — без денег.
