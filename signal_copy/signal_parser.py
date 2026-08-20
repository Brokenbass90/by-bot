# -*- coding: utf-8 -*-
"""Слой 1 парсера: только правила, без LLM. Демонстрация на реальном сообщении."""
import re, json
from dataclasses import dataclass, field, asdict
from typing import Optional, List

ALIASES = {
    "XAU/USD": "XAUUSD", "XAUUSD": "XAUUSD", "GOLD": "XAUUSD", "ЗОЛОТО": "XAUUSD",
    "EUR/USD": "EURUSD", "EURUSD": "EURUSD",
    "GBP/USD": "GBPUSD", "GBPUSD": "GBPUSD",
    "BTC/USD": "BTCUSD", "BTCUSD": "BTCUSD",
    "US30": "US30", "NAS100": "NAS100",
}
SIDE_RE = r"(BUY|SELL|ЛОНГ|ШОРТ|LONG|SHORT)"
NUM = r"[-+]?\d+(?:[.,]\d+)?"

def _num(s): return float(str(s).replace(",", "."))

@dataclass
class Signal:
    symbol: Optional[str] = None
    side: Optional[str] = None
    entry_min: Optional[float] = None
    entry_max: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profits: List[float] = field(default_factory=list)
    confidence: float = 0.0
    errors: List[str] = field(default_factory=list)
    raw: str = ""

def split_signals(text: str):
    """Одно сообщение может содержать несколько сигналов — режем по маркеру стороны."""
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines)
              if re.search(SIDE_RE, ln, re.I) and _find_symbol(ln)]
    if not starts:
        return [text]
    starts.append(len(lines))
    return ["\n".join(lines[starts[k]:starts[k+1]]) for k in range(len(starts)-1)]

def _find_symbol(line: str):
    up = line.upper()
    for alias in sorted(ALIASES, key=len, reverse=True):
        if alias in up:
            return ALIASES[alias]
    return None

def parse_one(block: str) -> Signal:
    sig = Signal(raw=block.strip())
    up = block.upper()

    sig.symbol = _find_symbol(up)

    m = re.search(SIDE_RE, up)
    if m:
        sig.side = "BUY" if m.group(1) in ("BUY", "ЛОНГ", "LONG") else "SELL"

    # стоп: строка со словом stop/sl
    m = re.search(r"(?:STOP\s*LOSS|STOPLOSS|\bSL\b)[^\d\-+]*(" + NUM + ")", up)
    if m:
        sig.stop_loss = _num(m.group(1))

    # цели: take profit N / TP / TPN  — собираем все
    for m in re.finditer(r"(?:TAKE\s*PROFIT|TP)\s*(?:\d(?![\d.,])\s*)?[^\d\-+]*(" + NUM + ")", up):
        v = _num(m.group(1))
        if v not in sig.take_profits:
            sig.take_profits.append(v)

    # вход: диапазон "a - b" в строке БЕЗ ключевых слов sl/tp
    consumed = {sig.stop_loss, *sig.take_profits}
    for ln in block.splitlines():
        lu = ln.upper()
        if re.search(r"STOP|\bSL\b|TAKE\s*PROFIT|\bTP\b", lu):
            continue
        rng = re.search(r"(" + NUM + r")\s*[-–—]\s*(" + NUM + ")", ln)
        if rng:
            a, b = _num(rng.group(1)), _num(rng.group(2))
            sig.entry_min, sig.entry_max = min(a, b), max(a, b)
            break
        solo = [_num(x) for x in re.findall(NUM, ln) if _num(x) not in consumed]
        if solo and sig.symbol and re.search(SIDE_RE, lu):
            sig.entry_min = sig.entry_max = solo[0]
            break
        if solo and not re.search(SIDE_RE, lu) and sig.entry_min is None and len(solo) == 1:
            sig.entry_min = sig.entry_max = solo[0]
            break

    _validate(sig)
    return sig

def _validate(s: Signal):
    required = {"symbol": s.symbol, "side": s.side,
                "entry": s.entry_min, "stop_loss": s.stop_loss}
    missing = [k for k, v in required.items() if v is None]
    for k in missing:
        s.errors.append(f"нет обязательного поля: {k}")
    if not s.take_profits:
        s.errors.append("нет ни одной цели (TP)")

    if not missing:
        if s.side == "BUY":
            if not (s.stop_loss < s.entry_min):
                s.errors.append(f"BUY: стоп {s.stop_loss} не ниже входа {s.entry_min}")
            if s.take_profits and not (max(s.take_profits) > s.entry_max):
                s.errors.append("BUY: цель не выше входа")
        else:
            if not (s.stop_loss > s.entry_max):
                s.errors.append(f"SELL: стоп {s.stop_loss} не выше входа {s.entry_max}")
            if s.take_profits and not (min(s.take_profits) < s.entry_min):
                s.errors.append("SELL: цель не ниже входа")
        # защита от опечатки на порядок
        dist = abs(s.entry_min - s.stop_loss) / s.entry_min
        if dist > 0.10:
            s.errors.append(f"стоп в {dist*100:.1f}% от входа — похоже на опечатку")

    filled = sum(v is not None for v in required.values()) + (1 if s.take_profits else 0)
    s.confidence = round(filled / 5.0, 2) if not s.errors else 0.0

def normalize(text: str) -> str:
    """Однострочные сигналы через / и | раскладываем в строки."""
    return re.sub(r"\s+[/|]\s+", "\n", text)

def parse_message(text: str) -> List[Signal]:
    t = normalize(text)
    return [parse_one(b) for b in split_signals(t)]

if __name__ == "__main__":
    MSG = """FOCUS | КАНАЛ, [19 авг. 2026 г., 11:37:46]:
✒️BUY XAU/USD

4353.7 - 4361.63

📌Stop loss (SL): 4347.11

• Take profit 1: 4392.66


✒️BUY EUR/USD

1.16034 - 1.15950

📌Stop loss (SL): 1.15900

• Take profit 1: 1.16148"""

    MSG2 = "GOLD BUY 4390-4393 / SL 4380 / TP 4410 / TP2 4425"

    for name, m in (("реальное сообщение канала", MSG), ("твой первый пример", MSG2)):
        print("=" * 62)
        print(name)
        print("=" * 62)
        for s in parse_message(m):
            d = asdict(s); d.pop("raw")
            print(json.dumps(d, ensure_ascii=False, indent=2))
            print("-" * 40)
