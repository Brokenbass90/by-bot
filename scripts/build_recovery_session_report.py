#!/usr/bin/env python3
"""Build the 2026-08-12 recovery report from pinned local evidence."""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/analytics/trading_recovery_20260812"


def load_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def atomic(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def build_artifact() -> dict:
    funding = load_json("reports/evidence/BYBIT_FUNDING_LISTINGS_ARCHIVE_VALIDATION_20260812.json")
    parity = load_json("reports/evidence/ATT1_DOT_ORDER_SIZE_PARITY_20260812.json")
    alpaca = load_json("reports/research/alpaca_honest_diagnostic_v1_20260810/receipt.json")
    alpaca_progress = load_json("research_lab/data/alpaca_pit_daily_v1/status.json")
    xsec = load_json("research_lab/results/xsec_recount/xsec_recount.json")
    xsec_holdout = load_json("research_lab/results/xsec_recount/symbol_holdout.json")
    pipeline = load_json("reports/research/six_day_crypto_pipeline_20260810/status.json")
    l2 = load_json("runtime/orderbook/alt24_density_v2/heartbeat.json")

    alpaca_runs = {
        (row["window"], row["arm"], float(row["cost_bps_per_side"])): row["summary"]
        for row in alpaca["results"]
    }
    bear = alpaca_runs[("bear_2022_survivor_proxy", "v38_successor_gated", 10.0)]
    recent = alpaca_runs[("live_universe_2024_2026_cached_intraday_proxy", "v38_successor_gated", 10.0)]
    recent_annual = (float(recent["final_equity"]) / 1000.0) ** 0.5 - 1.0

    fx = []
    with (ROOT / "reports/research/fx_h4_annual_reproduction_20260810/summary.csv").open(newline="", encoding="utf-8") as handle:
        fx = list(csv.DictReader(handle))
    fx_years = {}
    for row in fx:
        fx_years.setdefault(row["window"], 0.0)
        fx_years[row["window"]] += float(row["net_r"])

    # ATT1 is a mechanical translation of the narrow 8-major 18m anchor, not
    # a forecast.  Current effective risk = 0.44% global * 0.10 sleeve.
    att1_r_per_year = 30.20 / 1.5
    att1_effective_risk = 0.0044 * 0.10
    att1_illustrative_end = 1000.0 * (1.0 + att1_r_per_year * att1_effective_risk)

    scenarios = [
        {
            "name": "ATT1 Bybit canary",
            "stage": "CANARY",
            "initial_usd": 1000.0,
            "illustrative_end_usd": round(att1_illustrative_end, 2),
            "range_usd": None,
            "red_months": "2/12 in older narrow replay; live clean N still insufficient",
            "basis": "30.20R/18m narrow 8-major anchor × current effective 0.044% risk",
            "admissibility": "MECHANICAL_ONLY",
            "blocker": "20 clean post-fix closes and full reconciliation",
        },
        {
            "name": "XSEC neutral crypto",
            "stage": "SHADOW",
            "initial_usd": 1000.0,
            "illustrative_end_usd": 1075.0,
            "range_usd": [1075.0, 1095.0],
            "red_months": "not emitted by accepted search-only receipt",
            "basis": "pre-holdout CAGR 7.5%; symbol-holdout search CAGR 9.5%",
            "admissibility": "NOT_ADMISSIBLE",
            "blocker": "survivorship/PIT and funding cashflows unresolved; t-stat weak",
        },
        {
            "name": "Alpaca monthly equities",
            "stage": "SAFE_HOLD_PILOT",
            "initial_usd": 1000.0,
            "illustrative_end_usd": round(1000.0 * (1.0 + recent_annual), 2),
            "range_usd": [round(float(bear["final_equity"]), 2), round(1000.0 * (1.0 + recent_annual), 2)],
            "red_months": f"bear {bear['red_months']}/{bear['months']}; recent {recent['red_months']}/{recent['months']}",
            "basis": "stress 10bps: 2022 -2.89%; recent 24m +30.16% (14.09% CAGR)",
            "admissibility": "NOT_ADMISSIBLE",
            "blocker": "PIT pool incomplete and current-survivor selection remains",
        },
        {
            "name": "FX H4 candidate basket",
            "stage": "RESEARCH",
            "initial_usd": 1000.0,
            "illustrative_end_usd": None,
            "range_usd": [round(1000 * (1 + min(fx_years.values()) * 0.005), 2), round(1000 * (1 + max(fx_years.values()) * 0.005), 2)],
            "red_months": "not meaningful at 1-7 trades per variant",
            "basis": "mechanical 0.5%/R translation of +1.467R to +6.173R annual baskets",
            "admissibility": "NOT_ADMISSIBLE",
            "blocker": "all variants preflight false; swap/bid-ask/news absent",
        },
        {
            "name": "MPL / inplay next leg",
            "stage": "RESEARCH_BLOCKED",
            "initial_usd": 1000.0,
            "illustrative_end_usd": None,
            "range_usd": None,
            "red_months": "unknown",
            "basis": "no executable accepted backtest yet",
            "admissibility": "NO_ESTIMATE",
            "blocker": "MPL one-time holdout frozen but not unsealed; inplay same-close result revoked",
        },
    ]

    return {
        "schema_id": "trading_recovery_session_report_v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "answer_first": {
            "material_step_forward": True,
            "money_legs_now": 1,
            "safe_hold_pilots": 1,
            "promotion_ready_new_legs": 0,
            "summary": "Infrastructure and measurement advanced materially; no new money sleeve is honestly promotable yet.",
        },
        "overnight": {
            "research_jobs_visible": 10,
            "alpaca_pit": {
                "state": alpaca_progress.get("state"),
                "completed": len(alpaca_progress.get("completed") or []),
                "requested": alpaca_progress.get("requested"),
                "failed": len(alpaca_progress.get("failed") or {}),
            },
            "funding": {
                "symbols": funding["funding_file_count"],
                "observations": funding["funding_observation_count"],
                "integrity_pass": funding["integrity_pass"],
                "pit_ready": funding["pit_ohlcv_survivorship_resolved"],
            },
            "l2_alt24": {
                "state": l2.get("status"),
                "symbols": l2.get("symbol_count"),
                "observations": l2.get("observations"),
                "file_bytes": l2.get("file_bytes"),
                "free_bytes": l2.get("free_bytes"),
            },
            "six_day_pipeline": {
                "completed": pipeline.get("completed_cases"),
                "expected": pipeline.get("expected_cases"),
                "invalid": len(pipeline.get("invalid_cases") or []),
                "stage": pipeline.get("stage"),
            },
        },
        "quality_corrections": [
            "MPL contract rebuilt to next-open, isolated input and write-once result before one-time holdout.",
            "Inplay +0.2352R result revoked because the simulator entered on the signal-bar close; next-open replay required.",
            "XSEC modern metrics are quarantined; accepted scenario uses pre-holdout search only.",
            "Claude live env/try-except bug claims were not reproduced in the actual live state contract and were not patched.",
            f"DOT live/backtest size parity: {'PASS' if parity.get('pass') else 'FAIL'}.",
        ],
        "scenarios": scenarios,
        "xsec_evidence": {
            "preholdout_baseline": xsec.get("baseline_search"),
            "preholdout_symbol_holdout_180": xsec_holdout.get("clean_srch_180"),
            "modern_keys_excluded": True,
        },
        "next_gates": [
            {"priority": 1, "item": "Push immutable MPL commit, then one-time unseal", "eta": "same session after explicit push authorization"},
            {"priority": 2, "item": "Finish and validate Alpaca 1000-name pool", "eta": "hours for data; 1-2 days for repaired replay"},
            {"priority": 3, "item": "Funding-adjust XSEC and reconstruct closed-contract PIT universe", "eta": "2-5 engineering days, then shadow time"},
            {"priority": 4, "item": "Causal pre-holdout inplay replay", "eta": "1-2 engineering days; shadow only if it survives"},
            {"priority": 5, "item": "Accumulate clean ATT1 cohort", "eta": "about 47 calendar days at observed frequency"},
        ],
        "source_registry": [
            "reports/evidence/ATT1_DOT_ORDER_SIZE_PARITY_20260812.json",
            "reports/evidence/BYBIT_FUNDING_LISTINGS_ARCHIVE_VALIDATION_20260812.json",
            "research_lab/data/alpaca_pit_daily_v1/status.json",
            "runtime/orderbook/alt24_density_v2/heartbeat.json",
            "reports/research/alpaca_honest_diagnostic_v1_20260810/receipt.json",
            "research_lab/results/xsec_recount/xsec_recount.json",
            "research_lab/results/xsec_recount/symbol_holdout.json",
            "reports/research/fx_h4_annual_reproduction_20260810/summary.csv",
            "reports/research/six_day_crypto_pipeline_20260810/status.json",
        ],
    }


def render_markdown(a: dict) -> str:
    lines = [
        "# Recovery session — 12 August 2026",
        "",
        f"**Verdict:** {a['answer_first']['summary']}",
        "",
        "## $1,000 per sleeve: mechanical evidence, not a forecast",
        "",
        "| Sleeve | Stage | Mechanical year-end | Evidence range | Red months | Status |",
        "|---|---|---:|---:|---|---|",
    ]
    for row in a["scenarios"]:
        end = "—" if row["illustrative_end_usd"] is None else f"${row['illustrative_end_usd']:,.2f}"
        rng = "—" if row["range_usd"] is None else f"${row['range_usd'][0]:,.2f}–${row['range_usd'][1]:,.2f}"
        lines.append(f"| {row['name']} | {row['stage']} | {end} | {rng} | {row['red_months']} | {row['admissibility']} |")
    lines += [
        "",
        "The rows must not be added into a promised portfolio return: each has a different evidence grade and only ATT1 has current Bybit money authority. Alpaca remains a capped SAFE_HOLD pilot.",
        "",
        "## Material progress",
        "",
    ]
    lines += [f"- {x}" for x in a["quality_corrections"]]
    lines += ["", "## Next gates", ""]
    lines += [f"{x['priority']}. {x['item']} — {x['eta']}." for x in a["next_gates"]]
    lines += ["", "## Sources", ""] + [f"- `{p}`" for p in a["source_registry"]]
    return "\n".join(lines) + "\n"


def render_html(a: dict) -> str:
    cards = "".join(
        f"<article><h3>{html.escape(r['name'])}</h3><div class='stage'>{html.escape(r['stage'])}</div>"
        f"<div class='money'>{'—' if r['illustrative_end_usd'] is None else '$'+format(r['illustrative_end_usd'],',.2f')}</div>"
        f"<p>{html.escape(r['basis'])}</p><p class='warn'>{html.escape(r['blocker'])}</p></article>"
        for r in a["scenarios"]
    )
    gates = "".join(f"<li><b>{g['item']}</b><span>{g['eta']}</span></li>" for g in a["next_gates"])
    overnight = a["overnight"]
    return f"""<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Trading recovery 2026-08-12</title><style>
:root{{--bg:#0b1020;--card:#141b2e;--ink:#edf2ff;--muted:#9da9c7;--ok:#4ed6a1;--warn:#ffcc66;--line:#27324b}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(160deg,#0b1020,#10182a);color:var(--ink);font:15px/1.5 ui-sans-serif,system-ui;padding:32px}}
main{{max-width:1180px;margin:auto}}h1{{font-size:42px;margin:0 0 8px}}.lead{{color:var(--muted);max-width:800px;font-size:18px}}
.kpis,.grid{{display:grid;gap:14px}}.kpis{{grid-template-columns:repeat(4,1fr);margin:28px 0}}.grid{{grid-template-columns:repeat(3,1fr)}}
.kpi,article,.panel{{background:rgba(20,27,46,.92);border:1px solid var(--line);border-radius:16px;padding:18px}}.kpi b,.money{{display:block;font-size:28px;color:var(--ok)}}
.kpi span,.stage{{color:var(--muted)}}article h3{{margin:0}}article p{{color:var(--muted)}}.warn{{color:var(--warn)}}
.panel{{margin-top:18px}}li{{display:flex;justify-content:space-between;gap:20px;padding:10px 0;border-bottom:1px solid var(--line)}}li span{{color:var(--muted);text-align:right}}
footer{{color:var(--muted);margin-top:24px}}@media(max-width:850px){{.kpis,.grid{{grid-template-columns:1fr}}body{{padding:18px}}h1{{font-size:32px}}}}
</style></head><body><main><h1>Антикризисная сессия</h1><p class='lead'>{html.escape(a['answer_first']['summary'])} Сценарии ниже — механический перевод измерений на $1,000, не обещание доходности.</p>
<section class='kpis'><div class='kpi'><b>{overnight['funding']['symbols']}/137</b><span>funding symbols</span></div><div class='kpi'><b>{overnight['l2_alt24']['observations']:,}</b><span>L2 alt observations</span></div><div class='kpi'><b>{overnight['alpaca_pit']['completed']}/{overnight['alpaca_pit']['requested']}</b><span>Alpaca PIT downloaded</span></div><div class='kpi'><b>0</b><span>new money legs promoted</span></div></section>
<section class='grid'>{cards}</section><section class='panel'><h2>Следующие ворота</h2><ol>{gates}</ol></section>
<footer>Generated from pinned local receipts. Modern XSEC keys and same-close inplay figures are excluded.</footer></main></body></html>"""


def main() -> int:
    artifact = build_artifact()
    atomic(OUT / "artifact.json", json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic(OUT / "report.md", render_markdown(artifact))
    atomic(OUT / "report.html", render_html(artifact))
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
