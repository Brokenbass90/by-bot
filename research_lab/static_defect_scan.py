#!/usr/bin/env python3
"""СТАТИЧЕСКИЙ ПОИСК ДЕФЕКТОВ ПО ВСЕМ СТРАТЕГИЯМ — без запуска и без модели.

    python3 research_lab/static_defect_scan.py
    python3 research_lab/static_defect_scan.py strategies bot backtest

Ищет ровно те классы ошибок, которые мы уже поймали руками. Смысл в том,
чтобы узнать, единичные они или системные.

ПРАВИЛА (каждое выведено из найденного бага, а не придумано)

  E1  МИЛЛИСЕКУНДЫ + СЕКУНДЫ
      `expire_ts = tf_ts + окно * self._tf_seconds` в sloped_break_retest_v1:
      tf_ts в мс, _tf_seconds в секундах -> заявка жила 28.8 секунды вместо
      8 часов, стратегия не дала ни одной сделки за 42 прогона.
      Ищем сложение/вычитание, где с одной стороны имя с `ts`/`_ms`,
      с другой — с `sec`/`seconds`/`minutes`/`hours`, и нигде нет 1000.

  E2  СРАВНЕНИЕ ВРЕМЕНИ РАЗНЫХ МАСШТАБОВ
      `time.time()` (секунды) рядом с `*_ts` (миллисекунды).

  E3  АЛЛОУЛИСТ ИЗ ОДНОГО СИМВОЛА В ДЕФОЛТЕ
      `_env_csv_set("ASR1_SYMBOL_ALLOWLIST", "BCHUSDT")` в
      alt_support_reclaim_v1: нога выходила на первой строке 30 000 раз
      из 30 000, потому что торговала одну монету, которой у нас нет.

  E4  ПЕРЕУСЛОЖНЁННАЯ КОНЪЮНКЦИЯ
      Пять и более условий через `and` в одном `if`. В
      sloped_resistance_choch_v1 шестёрка не проходит целиком ни разу,
      и ни одна из 38 ручек этого не чинит.

  E5  ЧУЖОЙ ПРЕФИКС ENV
      В файле `alt_foo_v1.py` читается `BAR_SOMETHING` — след копипасты.
      Такая коллизия уже была: `BOUNCE1_*` и live-ASB1 делили переменные.

ЧТО ЭТО НЕ ДЕЛАЕТ
  Не доказывает, что находка — баг. Доказывает трассировка
  (`strategy_liveness_probe.py`). Здесь только «куда смотреть».
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

TS = re.compile(r"(^|_)(ts|ms)($|_)|_ts$|_ms$", re.I)
SEC = re.compile(r"sec(ond)?s?$|_seconds|_sec$|minutes?$|hours?$", re.I)


def names(node: ast.AST) -> list[str]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.append(n.id)
        elif isinstance(n, ast.Attribute):
            out.append(n.attr)
    return out


def has_1000(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            if n.value in (1000, 0.001, 1e3, 1e-3, 60000, 3_600_000, 86_400_000):
                return True
    return False


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except Exception as e:
        return [(0, "PARSE", f"не разобрался: {e}")]
    lines = src.splitlines()
    out: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        # E1 / E2
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            ln, rn = names(node.left), names(node.right)
            l_ts = any(TS.search(x) for x in ln)
            r_ts = any(TS.search(x) for x in rn)
            l_sec = any(SEC.search(x) for x in ln)
            r_sec = any(SEC.search(x) for x in rn)
            if ((l_ts and r_sec) or (r_ts and l_sec)) and not has_1000(node):
                out.append((node.lineno, "E1",
                            (lines[node.lineno - 1].strip()[:96]
                             if node.lineno <= len(lines) else "")))
        if isinstance(node, ast.Compare):
            all_n = names(node)
            if any(TS.search(x) for x in all_n):
                txt = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                if "time.time()" in txt and "1000" not in txt:
                    out.append((node.lineno, "E2", txt.strip()[:96]))

        # E4
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
            if len(node.values) >= 5:
                out.append((node.lineno, "E4",
                            f"конъюнкция из {len(node.values)} условий"))

        # E3
        if isinstance(node, ast.Call):
            fname = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
            if "csv_set" in fname and len(node.args) >= 2:
                a = node.args[1]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    v = a.value.strip()
                    if v and "," not in v and v.upper().endswith(("USDT", "USD", "PERP")):
                        out.append((node.lineno, "E3",
                                    f"дефолтный список из ОДНОГО символа: {v}"))

    return out


def scan_foreign_prefix(files: list[Path]) -> list[tuple[Path, str, str]]:
    """E5 в честном виде: чужой ПРЕФИКС, а не любой второй.

    Первая версия правила ловила TRAIL_, EMA_, RSI_ и выдавала 8 находок,
    из которых верных было ноль. Правило было плохим, и это выяснилось
    ровно тем же способом, что и всё остальное — проверкой находок.

    Теперь: у каждого файла определяем ЕГО канонический префикс (самый
    частый). Отмечаем файл, только если он >=3 раз использует канонический
    префикс ДРУГОГО файла. Так была найдена коллизия BOUNCE1_ и live-ASB1.
    """
    import collections
    canon: dict[Path, str] = {}
    used: dict[Path, collections.Counter] = {}
    for f in files:
        try:
            src = f.read_text(encoding="utf-8")
        except Exception:
            continue
        c = collections.Counter(re.findall(r'"([A-Z][A-Z0-9]{2,10})_[A-Z0-9_]+"', src))
        if not c:
            continue
        used[f] = c
        canon[f] = c.most_common(1)[0][0]
    owners = {v: k for k, v in canon.items()}
    out = []
    for f, c in used.items():
        mine = canon.get(f)
        for pref, n in c.items():
            if pref == mine or n < 3:
                continue
            owner = owners.get(pref)
            if owner is not None and owner != f:
                out.append((f, "E5",
                            f"использует `{pref}_` x{n} — канонический префикс "
                            f"{owner.name}; возможна коллизия переменных"))
    return out
    return out


def main() -> int:
    dirs = sys.argv[1:] or ["strategies"]
    files: list[Path] = []
    for d in dirs:
        files += sorted(Path(d).glob("*.py"))
    files = [f for f in files if not f.name.startswith("__")]

    counts: dict[str, int] = {}
    hits_by_file: dict[str, list] = {}
    foreign = scan_foreign_prefix(files)
    extra: dict[Path, list] = {}
    for f, code, txt in foreign:
        extra.setdefault(f, []).append((0, code, txt))
    for f in files:
        hits = scan_file(f) + extra.get(f, [])
        if hits:
            hits_by_file[str(f)] = hits
            for _, code, _ in hits:
                counts[code] = counts.get(code, 0) + 1

    print(f"просмотрено файлов: {len(files)}")
    if not counts:
        print("находок нет")
        return 0
    print("находок по типам: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print()

    order = {"E1": 0, "E2": 1, "E3": 2, "E5": 3, "E4": 4, "PARSE": 5}
    flat = [(order.get(c, 9), f, ln, c, txt)
            for f, hs in hits_by_file.items() for ln, c, txt in hs]
    flat.sort()
    for _, f, ln, code, txt in flat:
        if code == "E4":
            continue          # печатаем отдельно, их много и они лишь подсказка
        print(f"{code}  {f}:{ln}")
        if txt:
            print(f"      {txt}")

    e4 = [(f, ln, txt) for _, f, ln, c, txt in flat if c == "E4"]
    if e4:
        print(f"\nE4 переусложнённые конъюнкции ({len(e4)}) — подсказка, не диагноз:")
        for f, ln, txt in e4[:15]:
            print(f"      {f}:{ln}  {txt}")
        if len(e4) > 15:
            print(f"      ... ещё {len(e4) - 15}")

    print("\nЛюбая находка — «куда смотреть», а не «вот баг».")
    print("Подтверждать трассировкой: research_lab/strategy_liveness_probe.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
