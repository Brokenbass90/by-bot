#!/usr/bin/env python3
"""Persistent, read-only registry of negative strategy evidence.

The registry deliberately separates operational conversion failures from
profitability verdicts.  A sleeve producing no signal since restart is a
diagnostic lead, not proof that its trading idea is bad.  Stale/mixed sources
are recorded as data-quality gaps and never used for promotion.
"""
from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runtime" / "strategy_diagnostics"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _age_hours(path: Path) -> float | None:
    try:
        return max(0.0, (time.time() - path.stat().st_mtime) / 3600.0)
    except OSError:
        return None


def _id(source: str, strategy: str, phenotype: str, detail: str) -> str:
    raw = f"{source}|{strategy}|{phenotype}|{detail}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _finding(
    *, source: str, strategy: str, phenotype: str, detail: str,
    evidence: str, scope: str, safe_for_profit_verdict: bool,
    suggested_test: str, severity: str = "medium",
) -> dict[str, Any]:
    return {
        "id": _id(source, strategy, phenotype, detail),
        "source": source,
        "strategy": strategy,
        "phenotype": phenotype,
        "detail": detail,
        "evidence": evidence,
        "scope": scope,
        "safe_for_profit_verdict": safe_for_profit_verdict,
        "severity": severity,
        "suggested_test": suggested_test,
        "current": True,
        "status": "open",
    }


def collect_runtime_conversion(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = root / "runtime" / "live_mirror" / "bot_heartbeat.json"
    age = _age_hours(path)
    hb = _read_json(path)
    fresh = age is not None and age <= 0.25
    coverage = {"path": str(path.relative_to(root)), "age_hours": age, "fresh": fresh}
    if not hb or not fresh:
        return [], coverage
    counters = hb.get("runtime_counters") if isinstance(hb.get("runtime_counters"), dict) else {}
    prefixes = sorted({key[:-4] for key in counters if key.endswith("_try")})
    rows: list[dict[str, Any]] = []
    for prefix in prefixes:
        tries = int(counters.get(f"{prefix}_try") or 0)
        entries = int(counters.get(f"{prefix}_entry") or 0)
        signals = int(counters.get(f"{prefix}_signal") or 0)
        no_signal = int(counters.get(f"{prefix}_no_signal") or 0)
        if tries < 5 or entries > 0:
            continue
        reasons = []
        for key, value in counters.items():
            if key.startswith(f"{prefix}_ns_") and int(value or 0) > 0:
                reasons.append((key.removeprefix(f"{prefix}_ns_"), int(value)))
        reasons.sort(key=lambda item: -item[1])
        dominant = reasons[0] if reasons else ("unattributed", 0)
        phenotype = "signal_blocked_after_generation" if signals > 0 else "runtime_no_conversion"
        rows.append(_finding(
            source="fresh_live_heartbeat",
            strategy=prefix,
            phenotype=phenotype,
            detail=f"tries={tries} signals={signals} entries={entries} no_signal={no_signal} dominant={dominant[0]}:{dominant[1]}",
            evidence="fresh counters since current process restart",
            scope="operational_diagnostic_not_performance",
            safe_for_profit_verdict=False,
            suggested_test=(
                f"trace {prefix} dominant blocker `{dominant[0]}` by symbol/regime; "
                "compare with exact backtest counter before changing a threshold"
            ),
        ))
    return rows, coverage


def collect_trade_learning(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = root / "data" / "trade_learning_log.jsonl"
    age = _age_hours(path)
    coverage = {"path": str(path.relative_to(root)), "age_hours": age, "fresh": age is not None and age <= 168.0}
    if not path.exists():
        return [], coverage
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-500:]:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        for tag in list(row.get("tags") or []):
            grouped[(str(row.get("strategy") or "unknown"), str(tag))].append(row)
    findings = []
    for (strategy, tag), samples in grouped.items():
        if len(samples) < 3:
            continue
        symbols = Counter(str(row.get("symbol") or "") for row in samples)
        findings.append(_finding(
            source="trade_learning_log",
            strategy=strategy,
            phenotype=tag,
            detail=f"count={len(samples)} top_symbols={symbols.most_common(3)}",
            evidence="closed-trade learning records; verify cohort timestamps before use",
            scope="closed_trade_pattern",
            safe_for_profit_verdict=False,
            suggested_test=f"build preregistered {tag} ablation for {strategy}; preserve untouched OOS",
        ))
    return findings, coverage


def collect_scanner_blockers(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = root / "runtime" / "live_mirror" / "crypto_blocker" / "latest.json"
    age = _age_hours(path)
    payload = _read_json(path)
    fresh = age is not None and age <= 1.0
    coverage = {"path": str(path.relative_to(root)), "age_hours": age, "fresh": fresh}
    if not payload or not fresh:
        return [], coverage
    rows = []
    for strategy, sleeve in (payload.get("sleeves") or {}).items():
        if not isinstance(sleeve, dict) or int(sleeve.get("try") or 0) < 5:
            continue
        dominant = str(sleeve.get("dominant_reason") or "unattributed")
        rows.append(_finding(
            source="fresh_scanner_blocker_report",
            strategy=str(strategy),
            phenotype="scanner_to_strategy_blocker",
            detail=f"status={sleeve.get('status')} dominant={dominant} try={sleeve.get('try')} entry={sleeve.get('entry')}",
            evidence="scanner cards mapped to runtime sleeve counters",
            scope="scanner_runtime_parity",
            safe_for_profit_verdict=False,
            suggested_test=f"replay scanner card through {strategy} and attribute first rejecting predicate",
        ))
    return rows, coverage


def collect_research_contours(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Summarise machine-readable gates for active research contours.

    A fresh artifact proves collection only.  It does not prove an edge and
    cannot authorize capital without the contour-specific prospective gate.
    """
    rows: list[dict[str, Any]] = []
    sources = {
        "xsec": root / "runtime" / "xsec_v3_shadow" / "ledger.jsonl",
        "funding_frozen": root / "runtime" / "funding_positioning_post_n42_frozen_summary.json",
        "alpaca_adaptive": root / "runtime" / "alpaca_adaptive_v1_shadow_latest.json",
    }
    ages = {name: _age_hours(path) for name, path in sources.items()}
    fresh = {
        "xsec": ages["xsec"] is not None and ages["xsec"] <= 36.0,
        "funding_frozen": ages["funding_frozen"] is not None and ages["funding_frozen"] <= 1.0,
        "alpaca_adaptive": ages["alpaca_adaptive"] is not None and ages["alpaca_adaptive"] <= 30.0,
    }

    xsec_marks: list[float] = []
    xsec_path = sources["xsec"]
    if fresh["xsec"]:
        for line in xsec_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            mark = item.get("previous_phase_markout") if isinstance(item, dict) else None
            if isinstance(mark, dict) and mark.get("gross_return") is not None:
                xsec_marks.append(float(mark["gross_return"]) * 100.0)
    if xsec_marks and sum(xsec_marks) <= 0:
        rows.append(_finding(
            source="xsec_v3_shadow_ledger",
            strategy="xsec_v3",
            phenotype="negative_prospective_distribution",
            detail=(
                f"closed={len(xsec_marks)} positive={sum(value > 0 for value in xsec_marks)} "
                f"sum_markout_pct={sum(xsec_marks):.4f}"
            ),
            evidence="risk-zero daily phase markouts; gross return before a full executable-cost lifecycle",
            scope="prospective_research_distribution",
            safe_for_profit_verdict=False,
            suggested_test="finish the preregistered phase sample; decompose turnover, costs and long/short selection before promotion",
            severity="high",
        ))

    funding = _read_json(sources["funding_frozen"]) if fresh["funding_frozen"] else {}
    funding_closed = int(funding.get("closed") or 0)
    if funding:
        rows.append(_finding(
            source="funding_positioning_post_n42_frozen_summary",
            strategy="funding_positioning",
            phenotype="evidence_gate_pending",
            detail=(
                f"closed={funding_closed} pending_fill={int((funding.get('status_counts') or {}).get('pending_fill') or 0)} "
                f"universe_sha={str(funding.get('universe_sha256') or '')[:12]}"
            ),
            evidence="fresh frozen-universe prospective shadow; previous dynamic sample failed concentration gate",
            scope="prospective_research_collection",
            safe_for_profit_verdict=False,
            suggested_test="at N20-30 recompute capped distribution, p25, LOSO, beta, concentration and maker adverse selection",
            severity="info" if funding_closed < 20 else "high",
        ))

    alpaca = _read_json(sources["alpaca_adaptive"]) if fresh["alpaca_adaptive"] else {}
    if alpaca:
        pick_count = len(alpaca.get("picks") or [])
        rows.append(_finding(
            source="alpaca_adaptive_shadow_latest",
            strategy="alpaca_adaptive_v1",
            phenotype="decision_only_without_rotation_parity",
            detail=(
                f"mode={alpaca.get('mode')} picks={pick_count} "
                f"orders_sent={alpaca.get('orders_sent', False)}"
            ),
            evidence="fresh shadow selection artifact; it is not a broker fill or completed rotation receipt",
            scope="equities_shadow_lifecycle",
            safe_for_profit_verdict=False,
            suggested_test="reconcile broker fills, prove fractional stop replace, then complete one exact decision-to-rotation lifecycle",
            severity="medium",
        ))

    coverage = {
        "paths": {name: str(path.relative_to(root)) for name, path in sources.items()},
        "age_hours": ages,
        "fresh": all(fresh.values()),
        "fresh_by_source": fresh,
    }
    return rows, coverage


def merge(current: list[dict[str, Any]], previous: dict[str, Any]) -> dict[str, Any]:
    stamp = _now()
    old = {str(row.get("id")): row for row in list(previous.get("findings") or [])}
    seen: set[str] = set()
    for row in current:
        item_id = str(row["id"])
        seen.add(item_id)
        prior = old.get(item_id, {})
        row["first_seen_utc"] = prior.get("first_seen_utc") or stamp
        row["last_seen_utc"] = stamp
        row["occurrences"] = int(prior.get("occurrences") or 0) + 1
        if prior.get("status") in {"confirmed", "dismissed", "resolved"}:
            row["status"] = prior["status"]
            row["resolution_note"] = prior.get("resolution_note", "")
        old[item_id] = row
    for item_id, row in old.items():
        if item_id not in seen:
            row["current"] = False
    findings = sorted(old.values(), key=lambda row: (not bool(row.get("current")), str(row.get("strategy")), str(row.get("phenotype"))))
    return {
        "schema_id": "strategy_negative_evidence_registry_v1",
        "generated_at_utc": stamp,
        "authority": "diagnostic_only_no_live_mutation_no_profit_promise",
        "summary": {
            "total": len(findings),
            "current": sum(bool(row.get("current")) for row in findings),
            "profit_verdict_safe": sum(bool(row.get("current")) and bool(row.get("safe_for_profit_verdict")) for row in findings),
        },
        "findings": findings,
    }


def render_markdown(payload: dict[str, Any], coverage: dict[str, Any]) -> str:
    lines = [
        "# Strategy negative evidence registry", "",
        f"Generated: `{payload['generated_at_utc']}`", "",
        "This is a diagnostic queue, not a profitability verdict.", "",
        "## Source coverage", "",
        "| Source | Fresh | Age hours |",
        "|---|---:|---:|",
    ]
    for name, row in coverage.items():
        age = row.get("age_hours")
        if isinstance(age, dict):
            age_text = ", ".join(
                f"{key}={'-' if value is None else f'{value:.2f}'}"
                for key, value in sorted(age.items())
            )
        else:
            age_text = "-" if age is None else f"{age:.2f}"
        lines.append(f"| {name} | {row.get('fresh')} | {age_text} |")
    lines += ["", "## Current findings", "", "| Strategy | Phenotype | Evidence | Next falsifiable test |", "|---|---|---|---|"]
    for row in payload["findings"]:
        if not row.get("current"):
            continue
        lines.append(
            f"| {row['strategy']} | {row['phenotype']} | {row['detail']} | {row['suggested_test']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    collectors = {
        "runtime_conversion": collect_runtime_conversion,
        "trade_learning": collect_trade_learning,
        "scanner_blockers": collect_scanner_blockers,
        "research_contours": collect_research_contours,
    }
    current: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {}
    for name, collector in collectors.items():
        rows, source = collector(ROOT)
        current.extend(rows)
        coverage[name] = source
    path = OUT_DIR / "registry.json"
    payload = merge(current, _read_json(path))
    payload["source_coverage"] = coverage
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "registry.md").write_text(render_markdown(payload, coverage), encoding="utf-8")
    fields = ["id", "source", "strategy", "phenotype", "detail", "scope", "safe_for_profit_verdict", "severity", "status", "current", "first_seen_utc", "last_seen_utc", "occurrences", "suggested_test"]
    with (OUT_DIR / "registry.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(payload["findings"])
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
