#!/usr/bin/env python3
"""edinstvennyy_zapusk.py — запуск тени/сборщика строго в ОДНОМ экземпляре (13.10.2026, после двойного Breakout).
Код тени не меняется. Лаунчер (1) отказывается стартовать, если такой же скрипт уже работает (pgrep по пути скрипта),
(2) берёт flock на data/locks/<imya>.lock и через exec передаёт открытый дескриптор самой тени — замок живёт ровно
столько, сколько живёт процесс тени, и снимается ОС автоматически при его смерти (без stale-lock).

    .venv/bin/python research_lab/fabrika/edinstvennyy_zapusk.py breakout -- .venv/bin/python research_lab/breakout_ten.py --cikl

В screen:  screen -dmS breakout sh -c '.venv/bin/python research_lab/fabrika/edinstvennyy_zapusk.py breakout -- \
           .venv/bin/python research_lab/breakout_ten.py --cikl >> research_lab/data/breakout_ten.log 2>&1'
"""
import fcntl, os, re, subprocess, sys
from pathlib import Path

LOCKS = Path(__file__).resolve().parents[1] / "data" / "locks"


def main():
    if "--" not in sys.argv or sys.argv.index("--") != 2:
        sys.exit("использование: edinstvennyy_zapusk.py <imya> -- <команда...>")
    imya, cmd = sys.argv[1], sys.argv[3:]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", imya) or not cmd:
        sys.exit("плохое имя или пустая команда")
    skript = next((a for a in cmd if a.endswith(".py")), None)
    if skript:                                   # уже работает экземпляр, запущенный без лаунчера?
        r = subprocess.run(["pgrep", "-f", re.escape(skript) + "( |$)"], capture_output=True, text=True)
        chuzhie = [p for p in r.stdout.split() if int(p) != os.getpid()]
        if chuzhie:
            sys.exit(f"ОТКАЗ: {skript} уже работает (pid {', '.join(chuzhie)}) — второй экземпляр не запускаю")
    LOCKS.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCKS / f"{imya}.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(f"ОТКАЗ: замок {imya}.lock занят — второй экземпляр не запускаю")
    os.ftruncate(fd, 0); os.write(fd, f"{os.getpid()} {' '.join(cmd)}\n".encode())
    os.set_inheritable(fd, True)                # замок переходит в процесс тени
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
