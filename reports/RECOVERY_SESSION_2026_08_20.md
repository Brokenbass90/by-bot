# Антикризисная сессия — 20 августа 2026

## Итог

Шаг сделан не косметический: появился paper-контур лимитного исполнения ATT1, Inplay получил fail-close startup-gate, веб-позиция сверяется с прямой broker truth, ручной MT5-контур получил одноразовое owner-одобрение, найдено и закрыто смешение риска SLOPED/ATT1. Live не менялся.

Самый приятный результат — paper limit уже измерил первые три реальные ATT1-ситуации: 2 maker fill, 1 market fallback, средняя экономия +2.478 bps. Это ранний позитив, но пока не основание для live.

## Что реализовано и проверено

| Работа | Результат | Доказательство | Право |
|---|---|---|---|
| ATT1 limit execution | best bid/ask, 60s, market fallback, queue-aware fill | `runtime/att1_limit_execution_paper/status.json`; N=3, 66.7%, +2.478 bps | paper only |
| Inplay startup gate | hashes + sealed rows=0 + counts 32/40/62/81 | `runtime/inplay_prospective_shadow_v1/historical_frequency_startup_gate.json` после рестарта | shadow only |
| SLOPED sizing | `SLOPED_RISK_MULT` вместо ATT1 multiplier | regression test | code fix, not deployed |
| Web position console | multi-position, 1m–4h timeframe, broker reconciliation, XSS/stale-response fixes | 19 targeted tests in combined suite | read-only UI |
| MT5 manual signal copy | parse → fresh quotes → risk → owner prepare/execute token → reconcile | 5 standalone safety suites | local/demo-ready, live off |
| Bybit fees | linear maker 2.0/taker 5.5 bps; no rebate | signed GET read-only receipt from 20 Aug | fact for checked account/pairs |
| Password reset | hidden prompt, preserves TOTP/role | `tests/test_web_password_reset.py` | local admin action |

## Что из предложений Клода принято

- Нужен лимитный вход как execution challenger — принято и запущено только в paper.
- Нужна историческая frequency check до shadow — принято и сделано fail-close.
- Нужен единый «файл правды» — `docs/PRAVDA.md` превращён в текущий перезаписываемый snapshot.
- Нужны теневые тесты и непрерывный сбор — Inplay и paper-limit продолжаются; L2/tape collectors сохраняются.
- Нужна широкая M5 история — resumable job подготовлен.

## Что не принято без исправления

### Inplay и `BREAKOUT_*`

Подача переменных не требуется и исказила бы frozen contract. Exact replay уже даёт 0.91–2.31 raw signals/day на старых срезах. Свежий ноль — наблюдение рынка, а не доказанная поломка.

### ATT1 stop ×3.30/×6

Прямой запуск заблокирован. Исследовательская трансформация расширяет готовый stop и сохраняет старые TP; live-конструкция пересобирает stop через ATR и ставит TP заново. На 906 совпадающих сигналах медианы stop 12.08% против 8.53%, effective RR тоже различается. Сначала adapter parity, затем новый frozen replay.

### Три wide short shadow legs

Не запущены: отсутствует live-equivalent identity и общий collector. «Ноль риска» не делает неверный эксперимент полезным.

## Состояние по направлениям

### Crypto

- ATT1 не «сломана в ноль»: live execution работает, но исторический edge не подтверждён единым контрактом. Tiny-canary оставлен без изменения риска.
- Limiter paper — реальный путь улучшить экономику без изменения сигнала.
- Inplay — prospective candidate, но N=0. При исторической частоте N30 занимал бы примерно 13–33 дня; при текущей нулевой частоте даты нет.
- Wide stop — кандидат после parity repair.
- L2/microstructure — данные копятся; торговой ноги пока нет.

### Alpaca

Пилот защищён, но exact replay не закрыт в этой сессии. До полноценной ноги нужны: PIT universe, corporate actions, sector mapping, entry-relative stop exact replay, GTC deploy receipt и broker↔accounting parity. Ни +11%, ни +25.65% proxy нельзя переносить в ожидание live.

### XAU / FX / CFD

XAU-данные уже не блокер: 87,439 M5 и 7,291 H1 баров в pre-holdout окне. Следующий шаг — одна frozen session breakout/retest hypothesis с news blackout как отдельным challenger, а не ансамбль из десяти идей. FX/CFD идут после первого XAU replay и portability check.

### Web и встроенный AI

Страница позиции стала операторской: показывает несколько позиций, timeframe и прямую сверку broker↔bot. Если broker truth недоступна или конфликтует, статус `NOT_CONFIRMED/CONFLICT`, а не текст AI. Полный отказ от iframe и объединение остальных вкладок в единый SPA остаются следующим этапом.

### MT5 ручной ввод

Полезную работу Клода сохранено: локальный standalone-контур можно подключить к Telegram/web для ручных разметок. Исполнение по умолчанию выключено; нужны новый токен в `.env`, точный demo login и тип счёта. Секреты в Git не попали. Прямые close/breakeven endpoints отключены; любое действие требует короткоживущий одноразовый token.

## Ширина данных и непрерывность

- M5 exact pre-holdout: 8–9 majors готовы.
- Movers: 338 файлов, но это короткий текущий survivor-biased набор; он не заменяет wide PIT history.
- Wide137 downloader: подготовлен, resumable, sealed период не читает, останавливается при <50 GiB free.
- Tape/orderbook: несколько гигабайт публичных данных; они полезны для execution/microstructure, но не являются сами по себе edge.

## Следующие gates

1. Paper limit: N≥20, стабильная экономия после stress и совпадение модели с наблюдаемыми fills.
2. Inplay: продолжать frozen prospective; отдельный alert, если историческая frequency перестанет воспроизводиться.
3. ATT1/SBR1: normalized adapter parity по entry/SL/TP/exits/cooldown/regime/costs.
4. Alpaca: exact replay и GTC deploy receipt.
5. XAU: prereg + causal replay base/stress.
6. Worktree: reference-map 500+ файлов, затем thematic salvage/graveyard; никакой массовой зачистки.

## Чего не обещаю

Сейчас нельзя честно сложить «по $1000 на каждый контур» и назвать годовой доход: стратегии находятся на разных уровнях доказательности, а общие red months/correlation не измерены live-equivalent портфельным движком. Такой прогноз появится после минимум трёх сопоставимых validated legs.
