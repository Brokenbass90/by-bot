"""candidate_shortlist — отбирает кандидатов из JSON-прогонов раннеров.

Читает свежие чекпойнты `runtime/package_efficiency_*.json` и
`runtime/midterm_efficiency_*.json`, применяет КОНСЕРВАТИВНЫЕ пороги готовности и
делит стратегии на три корзины:
  * GO    — expectancy_R>0 И profit_factor>=PF_MIN И trades>=MIN_TRADES;
  * WATCH — в плюсе, но мало сделок / PF ниже порога (нужно больше данных);
  * CUT   — отрицательная экспектанси (не тратить риск).

Это НЕ замена promotion_gate (next-open/monthly/WF). Это первый объективный
фильтр: кого вообще нести в gate. На сервере запускать ПОСЛЕ полного прогона
раннеров с реальными комиссиями (PKG_COST_R).

Запуск:
    PYTHONPATH=. python3 backtest/candidate_shortlist.py
    PYTHONPATH=. python3 backtest/candidate_shortlist.py --pf 1.3 --trades 40
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"

PF_MIN = 1.20
MIN_TRADES = 30


def _latest(pattern: str) -> Optional[Path]:
    files = sorted(glob.glob(str(RUNTIME / pattern)))
    return Path(files[-1]) if files else None


def _load(path: Optional[Path]) -> Dict[str, dict]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pf(m: dict) -> float:
    v = m.get("profit_factor")
    if v == "inf":
        return float("inf")
    try:
        return float(v)
    except Exception:
        return 0.0


def _primary(m: dict) -> dict:
    """Поддержка двух форматов: плоского {trades,...} и нового {taker,maker}.
    Для решения берём taker (консервативно); maker сохраняем как подсказку."""
    if "taker" in m or "maker" in m:
        base = dict(m.get("taker") or {})
        mk = m.get("maker") or {}
        base["_maker_expR"] = float(mk.get("expectancy_R", 0) or 0)
        base["_maker_pf"] = mk.get("profit_factor")
        return base
    return m


def classify(rows: Dict[str, dict], pf_min: float, min_trades: int) -> Dict[str, List[Tuple[str, dict]]]:
    go, watch, cut = [], [], []
    for label, raw in rows.items():
        m = _primary(raw)
        if not m.get("trades"):
            continue
        exp = float(m.get("expectancy_R", 0) or 0)
        pf = _pf(m)
        n = int(m.get("trades", 0) or 0)
        maker_flip = exp <= 0 < float(m.get("_maker_expR", 0) or 0)
        if exp <= 0:
            # глубокий минус остаётся CUT; но если maker выводит в плюс — в WATCH-maker
            (watch if maker_flip else cut).append((label, m))
        elif pf >= pf_min and n >= min_trades:
            go.append((label, m))
        else:
            watch.append((label, m))
    keyf = lambda it: float(it[1].get("total_R", 0) or 0)
    return {"GO": sorted(go, key=keyf, reverse=True),
            "WATCH": sorted(watch, key=keyf, reverse=True),
            "CUT": sorted(cut, key=keyf, reverse=True)}


def _print_bucket(name: str, items: List[Tuple[str, dict]]):
    print(f"\n### {name} ({len(items)})")
    if not items:
        print("  —"); return
    print(f"  {'strategy':32s} {'trd':>5s} {'win%':>5s} {'expR_tk':>7s} {'PF':>5s} {'expR_mk':>8s}")
    for label, m in items:
        mk = m.get("_maker_expR")
        mk_s = f"{float(mk):>8.2f}" if mk is not None else f"{'—':>8s}"
        print(f"  {label:32s} {m.get('trades',0):>5d} {m.get('win_pct',0):>5.1f} "
              f"{float(m.get('expectancy_R',0)):>7.2f} {str(m.get('profit_factor','-')):>5s} {mk_s}")


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    pf_min = float(argv[argv.index("--pf") + 1]) if "--pf" in argv else PF_MIN
    min_trades = int(argv[argv.index("--trades") + 1]) if "--trades" in argv else MIN_TRADES

    pkg = _latest("package_efficiency_*.json")
    mid = _latest("midterm_efficiency_*.json")
    rows: Dict[str, dict] = {}
    rows.update(_load(pkg))
    rows.update(_load(mid))
    print("=== CANDIDATE SHORTLIST ===")
    print(f"package: {pkg.name if pkg else '—'}   midterm: {mid.name if mid else '—'}")
    print(f"пороги: expectancy_R>0, PF>={pf_min}, trades>={min_trades}  (стратегий: {len(rows)})")
    if not rows:
        print("\nНет JSON-прогонов в runtime/. Сначала прогнать раннеры "
              "(package_efficiency_run.py / midterm_efficiency_run.py).")
        return 0
    buckets = classify(rows, pf_min, min_trades)
    for name in ("GO", "WATCH", "CUT"):
        _print_bucket(name, buckets[name])
    out = RUNTIME / "candidate_shortlist_latest.json"
    out.write_text(json.dumps({k: [lab for lab, _ in v] for k, v in buckets.items()}, indent=2),
                   encoding="utf-8")
    print(f"\nJSON -> {out}")
    go = buckets["GO"]
    if go:
        print(f"\n→ В promotion_gate первыми: {', '.join(lab.split()[0] for lab, _ in go[:3])} "
              "(monthly/WF → fail-closed gate → shadow → canary $100).")
    else:
        print("\n→ GO пуст: на текущих данных/комиссиях доказанных кандидатов нет. "
              "Это честный результат — не поднимать риск ради активности.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
