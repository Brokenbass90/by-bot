"""ten_primery.py — сигналы-образцы для авто-теней (тесты/шаблон). Без рыночных данных."""


def kazhdyy_chas(now_ms, parametry):
    """Одно решение на каждый закрытый час: детерминированная заглушка."""
    h = now_ms // 3_600_000 * 3_600_000
    return [dict(sym=parametry.get("sym", "TESTUSDT"), napravlenie=1, izvestno_ms=h)]


def iz_budushchego(now_ms, parametry):
    return [dict(sym="X", napravlenie=1, izvestno_ms=now_ms + 60_000)]
