# Polymarket E2: consumer и действующий hook,4Nov2026

**HOOK_RUNTIME_PASS / WAITING_REAL_SIGNAL.** Consumer размещён там, где его
вызывают producer; полный реальный signal→quote→future outcome ещё НЕ завершён.

Реальный автоматический вызов psig(pid26905)4Nov12:42:36UTC, cycle observed
12:42:37.071UTC, exit0 зафиксирован12:42:51. Второй producer psig3(pid26906)
вызвал тот же consumer12:42:53UTC, observed12:42:53.849UTC, exit0 в12:43:23.
Оба журнала E2 вернули WAITING_REAL_SIGNAL, measured0/joined0/order_posts0.
Это фактический hook, не ручная имитация сигнала. Процессы Python3.13, целевые
тесты Python3.12; новый полноценный финансовый контур не включён.

## Что исправлено и связано

- Принят POLY_SIGNAL_V1/V1.1: chain/prefix/prereg/source quoteSHA, own first observation
  после fsync, one signal identity, immutable source/intake/actual book captures,
  manifest и отдельный after-fsync anchor. Повторный запуск не переоценивает старый вход.
- V3 token_id=null разрешается только через exact Gamma market+outcome_index и
  сравнение известной пары/токенаA из registry. Неоднозначность→UNKNOWN.
- Синтетический1−bid остаётся ценой producer для сравнения; actual ask/depth обоих
  токенов берутся заново из CLOB. Комиссия только из captured feeSchedule.
- Freshness120s перепроверяется на actual decision, не только перед HTTP.
- Официальный future join: condition selector DataAPI resolutions, status resolved,
  aware resolved_at, one-hot positive payouts, identity/manifest/frame hashes.
  Цена1/closed/endDate сами по себе не resolution. До исхода PENDING, без replay.
- Fair pending polling по давности попытки, включая ошибки GET; один global
  consumer flock и одинаковые namespace у default/selector. Outer hook300s не
  блокирует producer; после прерывания intake без полного manifest не переигрывается.
- **88 focusedPASS**. Независимое ограниченное ревью нашло5материальныхдефектов;
  все воспроизведены RED и исправлены. Post-fix тесты/root-review, не отдельный
  повторный independent signoff. Финансовых импортов/POST/кошелька/ключей нет.

## E1 → E2

Реальный E1 journal имел9строк/3ID,8нарушенийprev-chain, первое настроке2;
буквальныеbytes сохранены приватно, источник не ремонтировался. Claude подтвердил
три старых писателя и реализовал E2_20261104 сflock+IDdedup. Коммит33176e9 сообщён
владельцем; SHA обоих producer и writer module независимо проверены на диске и
в двух MANIFEST. Consumer привязан к этим exactSHA; drift→UNKNOWN, без repin.
E1 не подмешивается в новую эпоху. Старые поздно увиденные строки не стали входами.

## Развёртывание

Собственный launcher (create-exclusive, чужиефайлы не перезаписывались):
../bybit-bot-clean-v28/scripts/measure_polymarket_snapshot_v1.py
При --cycle-once он проверяет immutable runtime package и подставляет явные
research-root, source epochE2, state-root; без флага сеть не вызывается.
Package .private/poly_signal_cycle_20261104/runtime-838279bf47392cde,
manifestSHA838279bf47392cded2d9fda25a515bbd63d1f7aa997f355236494478da12466b;
launcherSHA57babb0eeb5cdc5a9dc887d3a49f628fa753ef94585b364c5f7806ee5c75efa4.
State .private/poly_signal_cycle_20261104/runtime-state/E2_20261104/<journal>/.
Существующий huk_codex_izmeritel.py/producer не менялся Codex; новыйservice/daemon
не устанавливался. Внешний lock hook сам по себе не atomic; нашglobalflock
проверен против параллельного selector/default и защищает именно обработку.

## Не закрытые ограничения

Новому E2 сигналу ещё предстоит actual measurement и будущий официальный join.
V3 source_sha покрывает исходную котировку, но не исходный sports frame. Пока
проверяются заявленные score/VPS/Mac timestamps; immutable frame reference отсутствует.
Поэтому sports_frame_provenance_verified=false и before_sports_FINAL=false;
открытый рынок не доказательство незавершённого матча. Rule/economicPASS не заявлен.
Модельныйnet не fill, не реальные комиссии/доходность/доступный заново капитал.

API отдельно проверен publicGET: известный ранее закрытый6668287 дал resolved,
ISOresolved_at и payouts[1000000,0]. Это проверка настоящей схемы API, не первый
реальный цикл и не подмена входа историей. Raw ответы сохранены приватно.

[Runtime/test/review evidence](evidence/poly_cycle_e2_20261104/actual-hook.json).
Официальные спецификации: [resolution state](https://docs.polymarket.com/api-reference/markets/get-resolution-state),
[market IDs/order](https://docs.polymarket.com/market-data/market-details).
