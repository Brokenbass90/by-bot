# Контракт Brain V0 (shadow) — «Regime Intelligence», 27.10.2026
Права: только запись. Не меняет сигналы, размеры, ордера и LIVE-исполнение Codex. Исполнитель — research-хук Claude (сторож, после 06:00 UTC).
## Что пишет
`data/brain_shadow_v1/rezhim_resheniya.jsonl`, append-only, одна строка на решение ноги: noga, sym, ts сигнала, side,
rezhim_v1 (BTC, последний закрытый 4h к концу часа сигнала), shirina_24ch (сигналы PUMP4 V1 по вселенной в [ts−24 ч; ts)),
istochnik (файл + sha256), t_zapisi. Исход дописывается отдельной строкой ISHOD из корректного источника ноги.
## Источники (только валидные)
PUMP4 — `data/pump4_vpered_zhurnal.jsonl` (непрерывный повтор); ETS2S — после подтверждения непрерывным повтором; ATT1 — тень (описательно);
KITY, Monthly — метка без фильтра (для карты на будущее).
## Какие решения из этого вырастают (только по своим prereg, не автоматически)
- PUMP4 F_SHIRINA (prereg 26.10, ≥ 40 сделок) и F_VOLNA_BULL (prereg 27.10, ≥ 15 отрезаемых и ≥ 40 оставляемых).
- PASS → предложение владельцу: фильтр перед TINY/LIVE PUMP4 (diff-конфиг, откат) → Codex.
## Исправлено сегодня
`fabrika/brain_pump4_noga.py` переведён с `pump4_pereschet` (журнал тени с пропусками) на `pump4_polnyy_povtor`.
