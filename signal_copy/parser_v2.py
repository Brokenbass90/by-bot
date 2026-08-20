# -*- coding: utf-8 -*-
"""Классификатор + парсер потока канала. Чистые правила, без LLM."""
import re, json
from dataclasses import dataclass, field, asdict
from typing import Optional, List

ALIASES = {
    "XAU/USD":"XAUUSD","XAUUSD":"XAUUSD","GOLD":"XAUUSD","ЗОЛОТО":"XAUUSD",
    "EUR/USD":"EURUSD","EURUSD":"EURUSD",
    "AUD/USD":"AUDUSD","AUDUSD":"AUDUSD",
    "USD/CHF":"USDCHF","USDCHF":"USDCHF",
    "GBP/USD":"GBPUSD","GBPUSD":"GBPUSD",
    "USD/JPY":"USDJPY","USDJPY":"USDJPY",
    "BTC/USD":"BTCUSD","BTCUSD":"BTCUSD",
}
SIDE_RE = r"\b(BUY|SELL|ЛОНГ|ШОРТ|LONG|SHORT)\b"
NUM     = r"\d+(?:[.,]\d+)?"

def _num(s): return float(str(s).replace(",", "."))

def find_symbol(text):
    up = text.upper()
    for a in sorted(ALIASES, key=len, reverse=True):
        if a in up: return ALIASES[a]
    return None

# ─────────────────────────── классификация ────────────────────────────
NOISE_MARKERS = ("ЭФИР","СТРИМ","ЗАПИСЬ","ССЫЛК","ПОДКЛЮЧЕН","СЕКРЕТНЫЙ КОД",
                 "СМОТРЕТЬ","БЛАГОДАРИМ","МСК")

def classify(text: str) -> str:
    up = text.upper()
    if re.search(SIDE_RE, up) and find_symbol(up) and re.search(r"STOP\s*LOSS|\bSL\b", up):
        return "SIGNAL"
    if "БЕЗУБЫТОК" in up or "БЕЗУБЫТК" in up or re.search(r"\bBE\b", up):
        return "MOVE_SL_BE"
    if up.strip().startswith("✅") or re.search(r"\bTP\s*\d\b.*POINT", up):
        return "RESULT_TP"
    if up.strip().startswith("❌") or re.search(r"^\W*STOP\s*LOSS", up):
        return "RESULT_SL"
    if any(k in up for k in NOISE_MARKERS):
        return "NOISE"
    # ни одного числа и ни одного тикера — это обычный текст, а не сломанный сигнал.
    # Важно: не дёргаем LLM на такое, чтобы не платить впустую.
    if not re.search(r"\d", text) and find_symbol(up) is None:
        return "PLAIN_TEXT"
    return "UNKNOWN"

# ───────────────────────────── парсинг ────────────────────────────────
@dataclass
class Parsed:
    kind: str = "UNKNOWN"
    symbol: Optional[str] = None
    side: Optional[str] = None
    entry_min: Optional[float] = None
    entry_max: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profits: List[float] = field(default_factory=list)
    claimed_points: Optional[float] = None
    needs_human: Optional[str] = None
    errors: List[str] = field(default_factory=list)

def parse(text: str) -> Parsed:
    kind = classify(text)
    p = Parsed(kind=kind)
    up = text.upper()
    p.symbol = find_symbol(up)

    if kind == "NOISE":
        return p

    if kind in ("MOVE_SL_BE", "RESULT_TP", "RESULT_SL"):
        m = re.search(r"([+-]?\d+)\s*POINT", up)
        if m: p.claimed_points = float(m.group(1))
        m = re.search(r"(?:STOP\s*LOSS|\bSL\b)\s*[^\d]*(" + NUM + ")", up)
        if m and kind == "RESULT_SL": p.stop_loss = _num(m.group(1))
        for m in re.finditer(r"\bTP\s*(?:\d(?![\d.,])\s*)?[^\d]*(" + NUM + ")", up):
            p.take_profits.append(_num(m.group(1)))
        if p.symbol is None:
            p.needs_human = "символ не назван — к какой позиции относится?"
        return p

    if kind != "SIGNAL":
        p.needs_human = "тип сообщения не распознан"
        return p

    m = re.search(SIDE_RE, up)
    p.side = "BUY" if m and m.group(1) in ("BUY","ЛОНГ","LONG") else "SELL"

    m = re.search(r"(?:STOP\s*LOSS|\bSL\b)[^\d]*(" + NUM + ")", up)
    if m: p.stop_loss = _num(m.group(1))

    for m in re.finditer(r"(?:TAKE\s*PROFIT|\bTP)\s*(?:\d(?![\d.,])\s*)?[^\d]*(" + NUM + ")", up):
        v = _num(m.group(1))
        if v not in p.take_profits: p.take_profits.append(v)

    # вход: первая строка с числами, где нет ключевых слов SL/TP и нет стороны
    for ln in text.splitlines():
        lu = ln.upper()
        if not re.search(r"\d", ln): continue
        if re.search(r"STOP|\bSL\b|TAKE\s*PROFIT|\bTP\b", lu): continue
        rng = re.search(r"(" + NUM + r")\s*[-–—]\s*(" + NUM + ")", ln)
        if rng:
            a, b = _num(rng.group(1)), _num(rng.group(2))
            p.entry_min, p.entry_max = min(a,b), max(a,b); break
        solo = re.findall(NUM, ln)
        if len(solo) == 1 and not re.search(SIDE_RE, lu):
            p.entry_min = p.entry_max = _num(solo[0]); break

    _validate(p)
    return p

def _validate(p: Parsed):
    req = {"symbol":p.symbol,"side":p.side,"entry":p.entry_min,"stop_loss":p.stop_loss}
    for k,v in req.items():
        if v is None: p.errors.append(f"нет поля: {k}")
    if not p.take_profits: p.errors.append("нет ни одной цели")
    if p.errors: return
    if p.side == "BUY":
        if p.stop_loss >= p.entry_min: p.errors.append("BUY: стоп не ниже входа")
        if max(p.take_profits) <= p.entry_max: p.errors.append("BUY: цель не выше входа")
    else:
        if p.stop_loss <= p.entry_max: p.errors.append("SELL: стоп не выше входа")
        if min(p.take_profits) >= p.entry_min: p.errors.append("SELL: цель не ниже входа")
    d = abs(p.entry_min - p.stop_loss)/p.entry_min
    if d > 0.10: p.errors.append(f"стоп в {d*100:.1f}% от входа — похоже на опечатку")


# ─────────────────── нарезка сообщения на отдельные сигналы ───────────────
def normalize(text: str) -> str:
    """Однострочные сигналы через " / " и " | " раскладываем в строки.
    Пробелы обязательны — иначе сломается XAU/USD."""
    return re.sub(r"\s+[/|]\s+", "\n", text)


def split_signals(text: str) -> list[str]:
    """Одно сообщение канала может содержать несколько сигналов подряд.
    Режем по строкам, где одновременно есть сторона и символ."""
    t = normalize(text)
    lines = t.splitlines()
    starts = [i for i, ln in enumerate(lines)
              if re.search(SIDE_RE, ln, re.I) and find_symbol(ln)]
    if not starts:
        return [t]
    blocks = []
    if starts[0] > 0 and any(l.strip() for l in lines[:starts[0]]):
        blocks.append("\n".join(lines[:starts[0]]))
    bounds = starts + [len(lines)]
    for k in range(len(bounds) - 1):
        blocks.append("\n".join(lines[bounds[k]:bounds[k + 1]]))
    return [b for b in blocks if b.strip()]

if __name__ == "__main__":
    msgs = [m.strip() for m in open("corpus.txt",encoding="utf-8").read().split("===MSG===")]
    W = {"SIGNAL":"СИГНАЛ","MOVE_SL_BE":"В БЕЗУБЫТОК","RESULT_TP":"ОТЧЁТ: ЦЕЛЬ",
         "RESULT_SL":"ОТЧЁТ: СТОП","NOISE":"ШУМ","UNKNOWN":"НЕ ПОНЯЛ"}
    counts = {}
    for i, m in enumerate(msgs, 1):
        p = parse(m)
        counts[p.kind] = counts.get(p.kind,0)+1
        head = m.splitlines()[0][:46].replace("\n"," ")
        line = f"{i:>2}. [{W[p.kind]:<12}] {head:<48}"
        if p.kind == "SIGNAL":
            line += f" {p.symbol} {p.side} {p.entry_min}-{p.entry_max} SL {p.stop_loss} TP×{len(p.take_profits)}"
            if p.errors: line += "  ⚠ " + "; ".join(p.errors)
        else:
            bits = []
            if p.symbol: bits.append(p.symbol)
            if p.claimed_points is not None: bits.append(f"{p.claimed_points:+.0f} pt")
            if p.take_profits: bits.append(f"цена {p.take_profits[0]}")
            if p.stop_loss: bits.append(f"цена {p.stop_loss}")
            if p.needs_human: bits.append("→ СПРОСИТЬ ЧЕЛОВЕКА: " + p.needs_human)
            line += " " + " · ".join(bits)
        print(line)
    print("\nИтого:", ", ".join(f"{W[k]}={v}" for k,v in counts.items()))
