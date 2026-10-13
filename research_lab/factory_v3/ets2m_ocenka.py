#!/usr/bin/env python3
"""ets2m_ocenka.py — запуск ЗАМОРОЖЕННОГО судьи Elder ETS2M_V2 (fabrika/ets2m_v2_kogorta.py --otsenit N) с сохранением вывода
как документа-квитанции data/factory_v3/kvitancii/ETS2M_V2_OKNO<N>.txt (+ sha256). Судья не меняется; вердикт по правилу
PREREG_TRI_TENI (прирост > 0, сигма > 2.5, знак на половинах, среднее R > 0) выносит CRO через sudya_most_v1.verdikt.
Пока когорта не набрана, судья сам печатает NOT_MEASURED — это тоже квитанция.

    .venv/bin/python research_lab/factory_v3/ets2m_ocenka.py 1
"""
import datetime as dt, hashlib, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; LAB = HERE.parent


def main(okno):
    out = subprocess.run([sys.executable, str(LAB / "fabrika" / "ets2m_v2_kogorta.py"), "--otsenit", str(okno)],
                         capture_output=True, text=True, cwd=str(LAB.parent), timeout=1800)
    txt = f"# {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} kod={out.returncode}\n{out.stdout}\n{out.stderr}"
    p = LAB / "data" / "factory_v3" / "kvitancii" / f"ETS2M_V2_OKNO{okno}.txt"; p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists(): p = p.with_name(f"{p.stem}_{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M}.txt")   # старые не переписываем
    p.write_text(txt); print(txt[-1500:]); print("квитанция:", p, hashlib.sha256(p.read_bytes()).hexdigest()[:16])


if __name__ == "__main__":
    main(int(sys.argv[1]))
