#!/usr/bin/env python3
"""make_queue_all.py — собрать очередь по ВСЕМ стратегиям, которые машина
умеет читать.

Зачем. Через машину прошло 14 стратегий из 92. Часть похоронена по
двум причинам, которые оказались нашими собственными ошибками:
пауза между сделками считалась в двенадцать раз длиннее живой,
а порог различимости был завышен в 2.4 раза. Значит хоронили
арифметикой, а не рынком. Всё надо перепроверить.

Скрипт сам находит класс, префикс и штатную паузу, делит паузу на 12
(часовой контур против пятиминутного) и пишет очередь.

Запуск:
    python3 research_lab/make_queue_all.py
    nohup ./research_lab/queue_all.sh &
"""
from __future__ import annotations
import ast, importlib, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"signals", "__init__", "base", "registry"}
TICK_RATIO = 12          # час / пять минут


def find_class(path: Path):
    """класс с методом maybe_signal"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    best = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if any(isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and x.name == "maybe_signal" for x in node.body):
                if best is None or node.name.endswith("Strategy"):
                    best = node.name
    return best


def find_prefix(text: str):
    m = re.findall(r'"([A-Z][A-Z0-9]{1,7})_(?:SYMBOL_ALLOWLIST|ALLOW_LONGS|'
                   r'ALLOW_SHORTS|COOLDOWN_BARS_5M|ENABLE|SIGNAL_LOOKBACK)"', text)
    if not m:
        return None
    return max(set(m), key=m.count)


def find_cooldown(text: str):
    m = re.search(r"cooldown_bars_5m: *int *= *(\d+)", text)
    return int(m.group(1)) if m else 0


def main():
    sys.path.insert(0, str(ROOT))
    rows, skipped = [], []
    for f in sorted((ROOT / "strategies").glob("*.py")):
        if f.stem in SKIP:
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        cls = find_class(f)
        pfx = find_prefix(text)
        if not cls:
            skipped.append((f.stem, "нет maybe_signal")); continue
        if not pfx:
            skipped.append((f.stem, "не нашёл префикс")); continue
        try:
            mod = importlib.import_module(f"strategies.{f.stem}")
            k = getattr(mod, cls, None)
            if k is None:
                skipped.append((f.stem, f"класс {cls} не грузится")); continue
            k()
        except Exception as e:
            skipped.append((f.stem, f"{type(e).__name__}")); continue
        cd = find_cooldown(text)
        rows.append((f.stem, cls, pfx, max(1, cd // TICK_RATIO) if cd else 0))

    out = ROOT / "research_lab" / "queue_all.sh"
    L = ["#!/bin/bash",
         "# ПОЛНАЯ ОЧЕРЕДЬ. Собрана автоматически: research_lab/make_queue_all.py",
         "#",
         "# Пауза между сделками поделена на 12 — штатное значение задано",
         "# в пятиминутках, а счётчик тикает раз в вызов.",
         "# Порог различимости в машине теперь считается по фактическому",
         "# разбросу конфигурации, а не по константе 1.03R.",
         "#",
         "# Запускать: nohup ./research_lab/queue_all.sh &",
         'cd "$(dirname "$0")/.."',
         "L=research_lab/queue_all.log",
         ": > $L",
         "run () {",
         '  echo "=== $(date -u +%F\\ %H:%M) старт $4 (пауза $5)" >> $L',
         "  nice -n 15 timeout 3600 python3 research_lab/research_machine.py \\",
         '      --strategy "$1" --cls "$2" --prefix "$3" \\',
         '      --data research_lab/data/h1 --tag "$4" --root . --cooldown "$5" \\',
         '      > "research_lab/rm_$4.log" 2>&1',
         '  echo "=== $(date -u +%F\\ %H:%M) готово $4" >> $L',
         '  sed -n \'/ОТСЕВ/,$p\' "research_lab/rm_$4.log" >> $L',
         "}"]
    for stem, cls, pfx, cd in rows:
        L.append(f"run {stem:<34} {cls:<36} {pfx:<7} {pfx.lower():<8} {cd}")
    L.append('echo "=== ПОЛНАЯ ОЧЕРЕДЬ ЗАВЕРШЕНА $(date -u)" >> $L')
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    os.chmod(out, 0o755)

    print(f"в очередь попало {len(rows)} стратегий:")
    for stem, cls, pfx, cd in rows:
        print(f"  {pfx:<7} {stem:<36} пауза {cd}")
    print(f"\nне попало {len(skipped)}:")
    for s, why in skipped[:40]:
        print(f"  {s:<40} {why}")
    print(f"\nочередь: {out}")


if __name__ == "__main__":
    main()
