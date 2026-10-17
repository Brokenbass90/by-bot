"""Unchanged pure entry function from pinned yadro; no bootstrap/judge/I/O.
Source SHA256: b413a48f67158ccb4a69c769bb1114065468a9610eace7d367400555d4821b66
"""

def ispolnenie(bary: list, i: int, short: bool, otstup: float, zhdat: int):
    """Лимитный вход. bary[i] — сигнальный бар.

    ("ispolnen", j, cena) — коснулись на баре j;
    ("net", None, None)   — окно ожидания ПРОШЛО и не коснулись;
    None                  — баров ещё не хватает, чтобы утверждать хоть что-то.

    Третий случай принципиален: «пока не знаю» нельзя записывать как «нет».
    """
    ref = float(bary[i][4])
    if ref <= 0 or otstup < 0:
        return ("net", None, None)
    limit = ref * (1.0 + otstup) if short else ref * (1.0 - otstup)
    okno = max(1, zhdat)
    for j in range(i + 1, min(i + 1 + okno, len(bary))):
        h, l = float(bary[j][2]), float(bary[j][3])
        if (h >= limit) if short else (l <= limit):
            return ("ispolnen", j, limit)
    if len(bary) >= i + 1 + okno:
        return ("net", None, None)
    return None
