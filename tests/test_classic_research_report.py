import csv
from pathlib import Path

from scripts.classic_research_report import build_report


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        for row in rows:
            w.writerow(row)


def test_build_report_from_run_dir(tmp_path):
    run = tmp_path / "portfolio_test"
    _write_csv(
        run / "summary.csv",
        [
            {
                "tag": "demo",
                "symbols": "BTCUSDT",
                "strategies": "inplay_breakout",
                "trades": 2,
                "net_pnl": 1.0,
                "profit_factor": 2.0,
                "winrate": 0.5,
                "max_drawdown": 1.0,
                "ending_equity": 101.0,
            }
        ],
    )
    _write_csv(
        run / "trades.csv",
        [
            {
                "strategy": "inplay_breakout",
                "symbol": "BTCUSDT",
                "side": "long",
                "entry_ts": 1770076800000,
                "exit_ts": 1770080400000,
                "pnl": 2.0,
                "R": 2.0,
                "regime": "",
            },
            {
                "strategy": "inplay_breakout",
                "symbol": "BTCUSDT",
                "side": "long",
                "entry_ts": 1772762400000,
                "exit_ts": 1772766000000,
                "pnl": -1.0,
                "R": -1.0,
                "regime": "",
            },
        ],
    )

    report = build_report(run, top=1, max_concurrent=1, bear_months={"2026-03"})

    assert len(report["candidates"]) == 1
    c = report["candidates"][0]
    assert c["summary"]["tag"] == "demo"
    assert c["monthly"]["2026-03"]["is_bear_month"] is True
    assert c["monthly_verdict"]["verdict"] == "FAIL"
    assert c["stack_comparison"]["bare"]["trades"] == 2


def test_build_report_from_interrupted_results_csv(tmp_path):
    sweep = tmp_path / "autoresearch_partial"
    worse = sweep / "run_worse"
    better = sweep / "run_better"
    for run, tag, pnl, pf in ((worse, "worse", -2.0, 0.8), (better, "better", 3.0, 1.4)):
        _write_csv(
            run / "summary.csv",
            [{
                "tag": tag,
                "symbols": "BTCUSDT",
                "strategies": "demo",
                "trades": 1,
                "net_pnl": pnl,
                "profit_factor": pf,
                "winrate": 1.0 if pnl > 0 else 0.0,
                "max_drawdown": 0.0 if pnl > 0 else 2.0,
                "ending_equity": 100.0 + pnl,
            }],
        )
        _write_csv(
            run / "trades.csv",
            [{
                "strategy": "demo",
                "symbol": "BTCUSDT",
                "side": "long",
                "entry_ts": 1770076800000,
                "exit_ts": 1770080400000,
                "pnl": pnl,
                "R": pnl,
                "regime": "",
            }],
        )

    _write_csv(
        sweep / "results.csv",
        [
            {"run_dir": str(worse), "passed": "False", "score": -10, "profit_factor": 0.8, "net_pnl": -2.0},
            {"run_dir": str(better), "passed": "True", "score": 10, "profit_factor": 1.4, "net_pnl": 3.0},
            {"run_dir": "", "passed": "False", "score": -1000000, "profit_factor": 0, "net_pnl": 0},
        ],
    )

    report = build_report(sweep, top=1, max_concurrent=None, bear_months=set())

    assert len(report["candidates"]) == 1
    assert report["candidates"][0]["summary"]["tag"] == "better"
