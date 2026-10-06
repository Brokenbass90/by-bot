"""Восстановление исходной когорты ETS2M (первые 900 входов) только из источника.

Причина расхождения: ядро пишет входы с полем zapisano (время записи). После вооружения
судьи (05.10 ~19:35 UTC) ядро дописало 3 входа с ts сигнала <= отсечки (позднее
обнаружение сигнала). Они вклинились в сортировку (ts,sym) и сдвинули первые 900.
Правило: взять строки с zapisano <= T, где T — последняя запись до вооружения,
отсортировать (ts,sym), первые 900 — это исходная когорта. Скрипт ищет T по пину,
ничего не пишет, исходы не читает.
"""
import hashlib, json, sys, datetime as D
from pathlib import Path

PIN = "0bcea9a398bac4af4509406a1e3ea5d67cafddd5d757935460422eb7c448a718"
CUT = 1790290800000
can = lambda v: json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

def main(path):
    rows, seen = [], set()
    for l in Path(path).read_bytes().splitlines():
        if not l.strip(): continue
        r = json.loads(l)
        if r["id"] in seen: continue
        seen.add(r["id"]); rows.append(r)
    for T in sorted({r["zapisano"] for r in rows}):
        sub = [r for r in rows if r["zapisano"] <= T]
        if len(sub) < 900: continue
        k = sorted(sub, key=lambda r: (r["ts"], r["sym"]))[:900]
        if hashlib.sha256(can(k)).hexdigest() == PIN:
            late = [r for r in rows if r["ts"] <= CUT and r["zapisano"] > T]
            print(json.dumps({"status": "RECOVERED", "zapisano_T": T,
                              "T_utc": D.datetime.utcfromtimestamp(T / 1000).isoformat(),
                              "cohort_sha256": PIN, "last_ts": k[-1]["ts"],
                              "late_rows": [{"id": r["id"], "sym": r["sym"], "ts": r["ts"], "zapisano": r["zapisano"]} for r in late]},
                             ensure_ascii=False, indent=1))
            return 0
    print(json.dumps({"status": "NOT_RECOVERED"})); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "research_lab/data/yadro/ETS2M/vhody.jsonl"))
