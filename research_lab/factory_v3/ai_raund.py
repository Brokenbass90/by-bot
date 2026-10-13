#!/usr/bin/env python3
"""ai_raund.py — раунд ИИ-исследователя на Маке (Ollama). Только предложения механизмов → NEW. 13.10.2026.

    .venv/bin/python research_lab/factory_v3/ai_raund.py                 # сухой прогон: копия реестра, ничего не пишет
    .venv/bin/python research_lab/factory_v3/ai_raund.py --n 5 --zapisat # записать прошедшие контракт в реестр (NEW)
    --model qwen3:8b   (по умолчанию — первая найденная qwen*/deepseek*)
Журнал раундов: research_lab/data/factory_v3/ai_raundy.jsonl
"""
import argparse, datetime as dt, json, shutil, sys, tempfile, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from reestr_v1 import Reestr, PUT_PO_UMOLCHANIYU
import ai_kontrakt_v1 as A


def modeli(host):
    with urllib.request.urlopen(f"{host}/api/tags", timeout=10) as r:
        return [m["name"] for m in json.loads(r.read()).get("models", [])]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=3); ap.add_argument("--model")
    ap.add_argument("--host", default="http://localhost:11434"); ap.add_argument("--zapisat", action="store_true")
    ap.add_argument("--zapros", default="Предложи механизм, независимый от уже убитых, на данных из каталога.")
    a = ap.parse_args()
    try: est = modeli(a.host)
    except Exception as e: sys.exit(f"Ollama недоступна на {a.host}: {e}")
    m = a.model or next((x for x in est if x.startswith(("qwen", "deepseek"))), est[0] if est else None)
    if not m: sys.exit("в Ollama нет моделей (ollama pull qwen3:8b)")
    if a.zapisat: r = Reestr()
    else:
        tmp = Path(tempfile.mkdtemp()) / "reestr_kopiya.jsonl"
        if PUT_PO_UMOLCHANIYU.exists(): shutil.copy(PUT_PO_UMOLCHANIYU, tmp)
        r = Reestr(tmp)
    rez = A.raund(r, A.klient_ollama(m, a.host), a.zapros, a.n)
    zap = dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), model=m, zapisano=a.zapisat, itogi=rez)
    log = HERE.parent / "data" / "factory_v3" / "ai_raundy.jsonl"; log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a") as f: f.write(json.dumps(zap, ensure_ascii=False) + "\n")
    print(f"модель {m}, {'ЗАПИСЬ в реестр' if a.zapisat else 'сухой прогон'}")
    for x in rez: print(" ", json.dumps(x, ensure_ascii=False)[:300])


if __name__ == "__main__":
    main()
