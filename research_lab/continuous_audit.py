#!/usr/bin/env python3
"""НЕПРЕРЫВНЫЙ АУДИТ: ищет баги и логические нестыковки, помнит, что уже видел.

    python3 research_lab/continuous_audit.py              # обычный прогон
    python3 research_lab/continuous_audit.py --full       # плюс проба живости (долго)
    python3 research_lab/continuous_audit.py --confirm ID # пометить находку подтверждённой
    python3 research_lab/continuous_audit.py --dismiss ID почему

На сервере:  0 4 * * *  cd /path/to/bot && python3 research_lab/continuous_audit.py --full

ЗАЧЕМ ИМЕННО ТАК
  Владелец прав: про большинство багов мы не подозреваем. Значит нужен
  не разовый разбор, а постоянный контур. Но у постоянного контура есть
  ровно одна смертельная болезнь — он превращается в обои: печатает
  сто находок, все их пролистывают, и он бесполезен. Аудитор проекта
  это уже проходил: 103 находки -> 28 -> 3.

  Поэтому здесь три предохранителя:

  1. ПАМЯТЬ. Каждая находка получает устойчивый id. Показываются только
     НОВЫЕ и ИСЧЕЗНУВШИЕ. Старые молчат, пока не изменятся.

  2. СТАТУС. Находку можно подтвердить или отклонить с причиной.
     Отклонённая больше не всплывает, но и не забывается.

  3. ГЕЙТ НА ПРАВИЛА. Считается доля подтверждённых по каждому правилу.
     Правило с долей ниже 10% помечается ШУМНЫМ и его находки уходят
     в конец. Это не теория: правило E5 в первой версии дало 8 находок
     и 0 верных.

ЧТО ЭТО НЕ ДЕЛАЕТ
  Не выносит вердиктов. Каждая находка — «куда смотреть», и у каждой
  есть поле «как опровергнуть». Подтверждение только трассировкой.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

LEDGER = Path("runtime/audit_ledger.json")
NOISY_THRESHOLD = 0.10
MIN_FOR_GATE = 5


def load() -> dict:
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"findings": {}, "runs": 0}


def save(db: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")


def fid(rule: str, where: str, what: str) -> str:
    return hashlib.sha1(f"{rule}|{where}|{what}".encode()).hexdigest()[:10]


def run(cmd: list[str], timeout: int = 1800) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout + p.stderr
    except Exception as e:
        return f"__ERROR__ {e}"


def collect_static() -> list[dict]:
    out = run([sys.executable, "research_lab/static_defect_scan.py",
               "strategies", "bot", "backtest", "research_lab", "scripts"])
    found, cur = [], None
    for line in out.splitlines():
        if line[:2] in ("E1", "E2", "E3", "E4", "E5") and " " in line:
            rule, where = line.split(None, 1)
            cur = {"rule": rule, "where": where.strip(), "what": "",
                   "how_to_refute": REFUTE.get(rule, "проверить трассировкой")}
            found.append(cur)
        elif cur is not None and line.startswith("      "):
            if not cur["what"]:
                cur["what"] = line.strip()[:160]
    return found


def collect_liveness(
    table: Path = Path("runtime/liveness_table.txt"),
    *,
    max_age_hours: float = 36.0,
    now_epoch: float | None = None,
) -> list[dict]:
    """Читает готовую таблицу, если она есть. Сам свип долгий — его
    запускает --full через scripts/liveness_sweep.sh."""
    t = table
    if not t.exists():
        return []
    now_epoch = float(now_epoch if now_epoch is not None else time.time())
    age_hours = max(0.0, (now_epoch - t.stat().st_mtime) / 3600.0)
    if age_hours > max_age_hours:
        return [{
            "rule": "L0",
            "where": str(t),
            "what": f"таблица живости устарела: {age_hours:.1f}ч > {max_age_hours:.1f}ч",
            "how_to_refute": "запустить supervisor с --full и убедиться, что mtime и результаты обновились",
        }]
    found = []
    for line in t.read_text(encoding="utf-8").splitlines()[2:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        name = parts[0]
        if "МЁРТВАЯ" in line:
            found.append({
                "rule": "L1", "where": f"strategies/{name}.py",
                "what": f"ноль сигналов на обоих символах ({parts[1]}/{parts[2]})",
                "how_to_refute": ("прогнать пробой на символе из ЕЁ аллоулиста: "
                                  "у btc_* и midterm-ног дефолтный список — BTC/ETH, "
                                  "и ноль на SOL/ADA ничего не значит"),
            })
        elif "ПРОПУСК" in line:
            found.append({
                "rule": "L2", "where": f"strategies/{name}.py",
                "what": "проба не смогла запустить стратегию",
                "how_to_refute": "посмотреть runtime/liveness_errors.txt — "
                                 "часто это не крипто-нога (alpaca/equities) "
                                 "или другой интерфейс, а не дефект",
            })
    return found


REFUTE = {
    "E1": "проверить единицы: tf_ts в мс, *_seconds в секундах — "
          "подтверждается трассировкой ветки протухания",
    "E2": "сравнить масштаб: time.time() в секундах, *_ts в миллисекундах",
    "E3": "если это btc_*-нога, один символ в дефолте — замысел, а не дефект",
    "E4": "аблация: если ни одна ручка не добавляет сигналов — структурная проблема",
    "E5": "проверить, читает ли нога чужие env на самом деле, а не совпадение имён",
}


def main() -> int:
    args = sys.argv[1:]
    db = load()

    if args and args[0] == "--confirm" and len(args) > 1:
        f = db["findings"].get(args[1])
        if not f:
            print("нет такой находки"); return 1
        f["status"] = "confirmed"; save(db)
        print(f"подтверждено: {f['rule']} {f['where']}"); return 0

    if args and args[0] == "--dismiss" and len(args) > 1:
        f = db["findings"].get(args[1])
        if not f:
            print("нет такой находки"); return 1
        f["status"] = "dismissed"
        f["why"] = " ".join(args[2:]) or "без причины"
        save(db)
        print(f"отклонено: {f['rule']} {f['where']} — {f['why']}"); return 0

    full = "--full" in args
    if full:
        print("полный прогон: свип живости (долго)...", flush=True)
        run(["bash", "scripts/liveness_sweep.sh"], timeout=7200)

    current = collect_static() + collect_liveness()
    seen_now = set()
    new_ids = []
    for f in current:
        i = fid(f["rule"], f["where"], f["what"])
        seen_now.add(i)
        if i not in db["findings"]:
            f.update({"status": "new", "first_seen": int(time.time())})
            db["findings"][i] = f
            new_ids.append(i)
        else:
            db["findings"][i]["last_seen"] = int(time.time())

    gone = [i for i, f in db["findings"].items()
            if i not in seen_now and f.get("status") in ("new", "confirmed")]
    for i in gone:
        db["findings"][i]["status"] = "gone"

    # гейт на шумные правила
    rule_stats: dict[str, list[int]] = {}
    for f in db["findings"].values():
        s = rule_stats.setdefault(f["rule"], [0, 0])
        s[0] += 1
        if f.get("status") == "confirmed":
            s[1] += 1
    noisy = {r for r, (tot, ok) in rule_stats.items()
             if tot >= MIN_FOR_GATE and ok / tot < NOISY_THRESHOLD}

    db["runs"] = db.get("runs", 0) + 1
    db["rule_stats"] = {
        rule: {"total": total, "confirmed": confirmed}
        for rule, (total, confirmed) in sorted(rule_stats.items())
    }
    db["noisy_rules"] = sorted(noisy)
    save(db)

    print(f"\nпрогон #{db['runs']}   находок всего {len(db['findings'])}, "
          f"из них новых {len(new_ids)}, исчезнувших {len(gone)}")

    if new_ids:
        print("\n── НОВОЕ (только это и требует внимания)")
        for i in sorted(new_ids, key=lambda x: (db["findings"][x]["rule"] in noisy,
                                                db["findings"][x]["rule"])):
            f = db["findings"][i]
            mark = "  [правило шумное]" if f["rule"] in noisy else ""
            print(f"  {i}  {f['rule']}  {f['where']}{mark}")
            if f["what"]:
                print(f"        {f['what']}")
            print(f"        как опровергнуть: {f['how_to_refute']}")
    else:
        print("\nновых находок нет — с прошлого прогона ничего не изменилось")

    if gone:
        print("\n── ИСЧЕЗЛО (починили или код удалён)")
        for i in gone:
            f = db["findings"][i]
            print(f"  {i}  {f['rule']}  {f['where']}")

    print("\n── ПРАВИЛА")
    for r, (tot, ok) in sorted(rule_stats.items()):
        tag = "ШУМНОЕ" if r in noisy else ""
        print(f"  {r}: находок {tot}, подтверждено {ok} "
              f"({ok/tot*100:.0f}%) {tag}")
    print("\nподтвердить:  python3 research_lab/continuous_audit.py --confirm <id>")
    print("отклонить:    python3 research_lab/continuous_audit.py --dismiss <id> причина")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
