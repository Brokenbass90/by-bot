"""stil.py — канонический стиль отчётов Trading OS = стиль крипто-бота (smart_pump_reversal_bot._make_trade_chart)."""
C = dict(bg="#0b1020", plot="#0f172a", panel="#111827", ink="#e2e8f0", muted="#94a3b8", grid="#94a3b8", spine="#334155",
         up="#22c55e", down="#ef4444", entry="#38bdf8", stop="#ef4444", target="#22c55e", exitc="#f59e0b", geom="#facc15")
OK, NET_, NEIZV = "✓", "✗", "?"


def znak(x, ccy="", nd=2):
    """Деньги со знаком и стрелкой — смысл не только цветом."""
    if x is None: return "н/д"
    s = f"{abs(x):,.{nd}f}{(' ' + ccy) if ccy else ''}"
    return ("▲ +" if x > 0 else "▼ −" if x < 0 else "± ") + s


def dlit(ms):
    if ms is None: return "н/д"
    s = int(ms // 1000)
    if s < 120: return f"{s} с"
    m = s // 60
    if m < 120: return f"{m} мин"
    h = m // 60
    return f"{h} ч {m % 60} мин" if h < 48 else f"{h // 24} д {h % 24} ч"


PRICHINY = {   # машинные причины → по-русски (неизвестная причина показывается как есть, не скрывается)
    "DISPATCH_PREFLIGHT:POST_GO_DISPATCH_DEADLINE": "не уложились в окно отправки 60 с",
    "SIXTY_SECOND_TEN_LEG_SEQUENTIAL_ENTRY_BUDGET_INSUFFICIENT": "60 с мало для 10 последовательных ног",
    "TERMS_NOT_ACCEPTED": "биржа требует принять условия инструмента",
    "PRICE_ENVELOPE": "цена вышла из допустимого конверта",
    "EC_NoImmediateQtyToFill": "IOC не исполнился: на цене лимита не оказалось объёма",
    "FRESH_BLOCKED_GROSS_CAP": "минимальный объём корзины по шагам лотов выше потолка",
}


def prichina(kod):
    return PRICHINY.get(str(kod), str(kod))
