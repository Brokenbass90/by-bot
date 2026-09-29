#!/usr/bin/env python3
"""vps_sostoyanie.py — ОДНО определение того, что такое «состояние».

Печатает JSON. Используется дважды и одним и тем же кодом:
  * на Mac перед переносом  → эталон (vps_etalon.sh);
  * на VPS до запуска       → факт  (vps_sverka.sh).

Смысл в том, чтобы эталон и проверка не могли разойтись: если завтра
добавится новый вид состояния, он добавится здесь один раз и сразу
попадёт в обе стороны сверки.

Ничего не пишет и ничего не импортирует тяжёлого: обычный python3.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent
KOREN = LAB.parent


def strok(p):
    f = KOREN / p
    if not f.exists():
        return None
    with open(f, encoding="utf-8", errors="ignore") as fh:
        return sum(1 for _ in fh)


def sha(p):
    f = KOREN / p
    if not f.exists():
        return None
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for kus in iter(lambda: fh.read(1 << 16), b""):
            h.update(kus)
    return h.hexdigest()[:16]


def faylov(p, shablon="*"):
    d = KOREN / p
    return len(list(d.rglob(shablon))) if d.exists() else None


def gruz(p, klyuch=None, umolch=None):
    f = KOREN / p
    if not f.exists():
        return umolch
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        return umolch
    return d if klyuch is None else d.get(klyuch, umolch)


s = {}

# ── ETS2M: когорта не имеет права начаться заново ────────────────────
s["ets2m_vhodov"] = strok("research_lab/data/yadro/ETS2M/vhody.jsonl")
s["ets2m_ishodov"] = strok("research_lab/data/yadro/ETS2M/ishody.jsonl")
s["ets2m_ispolneniy"] = strok("research_lab/data/yadro/ETS2M/ispolnenie.jsonl")
s["ets2m_epoha_sha"] = sha("research_lab/data/yadro/ETS2M/epoha.json")

# ── SILA: момент старта — самое хрупкое во всём переносе ─────────────
s["sila_nachalo"] = gruz("research_lab/data/ten_SILA_sostoyanie.json", "nachalo")
s["sila_resheniy"] = strok("research_lab/data/ten_SILA.jsonl")

# ── фабрика: реестр, очередь, вердикты ───────────────────────────────
s["fabrika_verdiktov"] = strok("research_lab/fabrika/verdikty.jsonl")
och = gruz("research_lab/fabrika/ochered.json", "ochered", [])
s["fabrika_punktov"] = len(och) if och is not None else None
sost = {}
for it in och or []:
    k = it.get("sostoyanie", "?")
    sost[k] = sost.get(k, 0) + 1
s["fabrika_sostoyaniya"] = dict(sorted(sost.items()))
s["fabrika_rezultatov"] = faylov("research_lab/fabrika/rezultaty")
s["fabrika_teney"] = faylov("research_lab/fabrika/teni", "*.json")

# ── канонический реестр ──────────────────────────────────────────────
r = gruz("research_lab/data/reestr.json", umolch=None)
s["reestr_zapisey"] = len(r) if isinstance(r, list) else (len(r) if isinstance(r, dict) else None)
s["reestr_istorii_strok"] = strok("research_lab/data/reestr_istoriya.jsonl")

# ── Polymarket: сопоставление уже собрано, пересобирать нечем ────────
s["poly_rynkov_v_istorii"] = faylov("research_lab/data/poly/istoriya", "*.json")
s["poly_otobrano_sha"] = sha("research_lab/data/poly/otobrano.json")

# ── данные, от которых зависит отпечаток и состояния очереди ─────────
s["pit_daily_faylov"] = faylov("research_lab/data/pit_daily")
s["basis_faylov"] = faylov("research_lab/data/basis")
s["akcii_barov"] = faylov("research_lab/data/alpaca_pit_daily_v1/bars")

print(json.dumps(s, ensure_ascii=False, indent=2, sort_keys=True))
