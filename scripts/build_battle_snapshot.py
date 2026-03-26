#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parent.parent


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_latest(pattern: str) -> Path | None:
    matches = sorted(ROOT.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _read_csv_rows(path: Path) -> List[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _read_single_row(path: Path) -> dict:
    rows = _read_csv_rows(path)
    if not rows:
        raise ValueError(f"empty csv: {path}")
    return rows[0]


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _monthly_stats_from_trades(path: Path) -> dict:
    month_net: "OrderedDict[str, float]" = OrderedDict()
    rows = _read_csv_rows(path)
    for row in rows:
        ts_raw = row.get("exit_ts") or row.get("entry_ts") or "0"
        ts_ms = _to_int(ts_raw, 0)
        if ts_ms <= 0:
            continue
        if ts_ms > 10_000_000_000:
            ts_sec = ts_ms / 1000.0
        else:
            ts_sec = float(ts_ms)
        month = datetime.fromtimestamp(ts_sec, tz=timezone.utc).strftime("%Y-%m")
        month_net[month] = month_net.get(month, 0.0) + _to_float(row.get("pnl"), 0.0)

    pos = sum(1 for v in month_net.values() if v > 0)
    neg = sum(1 for v in month_net.values() if v < 0)
    zero = sum(1 for v in month_net.values() if v == 0)
    total = len(month_net)
    return {
        "months_total": total,
        "pos_months": pos,
        "neg_months": neg,
        "zero_months": zero,
        "pos_month_share_pct": round((100.0 * pos / total), 2) if total else 0.0,
        "net_total": round(sum(month_net.values()), 6),
    }


def _load_env_role_map(path: Path) -> Dict[str, str]:
    role_map: Dict[str, str] = {}
    if not path.exists():
        return role_map
    vars_map: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        vars_map[key.strip()] = value.strip()
    for combo in vars_map.get("FOREX_ACTIVE_COMBOS", "").split(","):
        combo = combo.strip()
        if combo:
            role_map[combo] = "ACTIVE"
    for combo in vars_map.get("FOREX_CANARY_COMBOS", "").split(","):
        combo = combo.strip()
        if combo:
            role_map[combo] = "CANARY"
    return role_map


def _apply_rule(metrics: dict, rule: dict) -> List[str]:
    reasons: List[str] = []
    for key, expected in rule.items():
        if key.startswith("min_"):
            metric_key = key[4:]
            actual = _to_float(metrics.get(metric_key), float("nan"))
            if actual < float(expected):
                reasons.append(f"{metric_key}<{expected}")
        elif key.startswith("max_"):
            metric_key = key[4:]
            actual = _to_float(metrics.get(metric_key), float("nan"))
            if actual > float(expected):
                reasons.append(f"{metric_key}>{expected}")
        elif key.startswith("required_"):
            metric_key = key[9:]
            actual = str(metrics.get(metric_key, "")).strip()
            if actual != str(expected):
                reasons.append(f"{metric_key}!={expected}")
        elif key.startswith("allowed_"):
            metric_key = key[8:]
            actual = str(metrics.get(metric_key, "")).strip()
            allowed = {str(x) for x in expected}
            if actual not in allowed:
                reasons.append(f"{metric_key}_not_allowed")
        else:
            reasons.append(f"unsupported_rule:{key}")
    return reasons


def _evaluate_crypto(candidate: dict, rule: dict) -> Tuple[dict, List[str]]:
    out: dict = {}
    reasons: List[str] = []
    pairs = [
        ("base", candidate.get("base_summary_glob"), candidate.get("base_trades_glob")),
        ("stress", candidate.get("stress_summary_glob"), candidate.get("stress_trades_glob")),
    ]
    for prefix, summary_glob, trades_glob in pairs:
        summary_path = _resolve_latest(str(summary_glob or ""))
        trades_path = _resolve_latest(str(trades_glob or ""))
        if summary_path is None or trades_path is None:
            reasons.append(f"missing_{prefix}_artifact")
            continue
        summary = _read_single_row(summary_path)
        monthly = _monthly_stats_from_trades(trades_path)
        out[f"{prefix}_summary_path"] = str(summary_path.relative_to(ROOT))
        out[f"{prefix}_trades_path"] = str(trades_path.relative_to(ROOT))
        out[f"{prefix}_net_pnl"] = round(_to_float(summary.get("net_pnl"), 0.0), 6)
        out[f"{prefix}_profit_factor"] = round(_to_float(summary.get("profit_factor"), 0.0), 6)
        out[f"{prefix}_drawdown"] = round(_to_float(summary.get("max_drawdown"), 0.0), 6)
        out[f"{prefix}_trades"] = _to_int(summary.get("trades"), 0)
        out[f"{prefix}_pos_month_share_pct"] = _to_float(monthly.get("pos_month_share_pct"), 0.0)
        out[f"{prefix}_pos_months"] = _to_int(monthly.get("pos_months"), 0)
        out[f"{prefix}_neg_months"] = _to_int(monthly.get("neg_months"), 0)
        out[f"{prefix}_months_total"] = _to_int(monthly.get("months_total"), 0)
    reasons.extend(_apply_rule(out, rule))
    return out, reasons


def _evaluate_forex(candidate: dict, rule: dict) -> Tuple[dict, List[str]]:
    csv_path = ROOT / str(candidate["csv"])
    rows = _read_csv_rows(csv_path)
    row = next(
        (
            r
            for r in rows
            if (r.get("pair") or "").strip().upper() == str(candidate["pair"]).upper()
            and (r.get("strategy") or "").strip() == str(candidate["strategy"])
        ),
        None,
    )
    if row is None:
        return {"csv_path": str(csv_path.relative_to(ROOT))}, ["missing_forex_row"]

    out = {
        "csv_path": str(csv_path.relative_to(ROOT)),
        "status": (row.get("status") or "").strip(),
        "stress_net": round(_to_float(row.get("stress_net"), 0.0), 4),
        "stress_trades": _to_int(row.get("stress_trades"), 0),
        "stress_dd": round(_to_float(row.get("stress_dd"), 0.0), 4),
        "stress_ret_pct": round(_to_float(row.get("stress_ret_pct"), 0.0), 4),
        "month_both_positive_share_pct": round(_to_float(row.get("month_both_positive_share_pct"), 0.0), 2),
        "roll_both_positive_share_pct": round(_to_float(row.get("roll_both_positive_share_pct"), 0.0), 2),
        "pos_months": _to_int(row.get("pos_months"), 0),
        "neg_months": _to_int(row.get("neg_months"), 0),
    }
    reasons = _apply_rule(out, rule)

    env_path_raw = candidate.get("env_path")
    expected_env_role = candidate.get("expected_env_role")
    if env_path_raw and expected_env_role:
        env_path = ROOT / str(env_path_raw)
        combo_id = f"{candidate['pair']}@{candidate['strategy']}"
        role_map = _load_env_role_map(env_path)
        actual_role = role_map.get(combo_id, "")
        out["env_role"] = actual_role or "MISSING"
        if actual_role != str(expected_env_role):
            reasons.append(f"env_role!={expected_env_role}")
    return out, reasons


def _evaluate_equities(candidate: dict, rule: dict) -> Tuple[dict, List[str]]:
    csv_path = ROOT / str(candidate["csv"])
    rows = _read_csv_rows(csv_path)
    row = next(
        (
            r
            for r in rows
            if (r.get("ticker") or "").strip().upper() == str(candidate["ticker"]).upper()
            and (r.get("strategy") or "").strip() == str(candidate["strategy"])
        ),
        None,
    )
    if row is None:
        return {"csv_path": str(csv_path.relative_to(ROOT))}, ["missing_equities_row"]

    out = {
        "csv_path": str(csv_path.relative_to(ROOT)),
        "state": (row.get("state") or "").strip().upper(),
        "both_positive_share_pct": round(_to_float(row.get("last_both_positive_share_pct"), 0.0), 2),
        "stress_net_cents": round(_to_float(row.get("last_stress_net_cents"), 0.0), 4),
        "stress_trades": _to_int(row.get("last_stress_trades"), 0),
        "pass_streak": _to_int(row.get("pass_streak"), 0),
        "last_reason": (row.get("last_reason") or "").strip(),
    }
    reasons = _apply_rule(out, rule)
    return out, reasons


def _evaluate_candidate(candidate: dict, rules: dict) -> dict:
    rule_name = str(candidate["rule_profile"])
    rule = rules.get(rule_name)
    if rule is None:
        return {
            "id": candidate["id"],
            "stack": candidate["stack"],
            "stage": candidate["stage"],
            "rule_profile": rule_name,
            "decision": "BLOCKED",
            "reasons": [f"missing_rule:{rule_name}"],
            "metrics": {},
        }

    source_type = str(candidate["source_type"])
    if source_type == "crypto_pair":
        metrics, reasons = _evaluate_crypto(candidate, rule)
    elif source_type == "forex_stability":
        metrics, reasons = _evaluate_forex(candidate, rule)
    elif source_type == "equities_state":
        metrics, reasons = _evaluate_equities(candidate, rule)
    else:
        metrics, reasons = {}, [f"unsupported_source:{source_type}"]

    return {
        "id": candidate["id"],
        "stack": candidate["stack"],
        "stage": candidate["stage"],
        "rule_profile": rule_name,
        "decision": "READY" if not reasons else "BLOCKED",
        "reasons": reasons,
        "metrics": metrics,
    }


def _write_text(path: Path, payload: dict) -> None:
    lines: List[str] = []
    lines.append(f"generated_utc={payload['generated_utc']}")
    lines.append(f"ready={len(payload['ready_ids'])}")
    lines.append(f"blocked={len(payload['blocked_ids'])}")
    lines.append("")
    by_stack: Dict[str, List[dict]] = defaultdict(list)
    for item in payload["candidates"]:
        by_stack[item["stack"]].append(item)
    for stack in sorted(by_stack):
        lines.append(f"[{stack}]")
        for item in by_stack[stack]:
            state = item["decision"]
            reasons = ",".join(item["reasons"]) if item["reasons"] else "-"
            lines.append(f"{state} {item['id']} stage={item['stage']} reasons={reasons}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build machine-readable battle snapshot from crypto/forex/equities artifacts.")
    ap.add_argument("--rules", default="configs/battle_filter_rules.json")
    ap.add_argument("--candidates", default="configs/battle_candidates.json")
    ap.add_argument("--out-prefix", default="docs/battle_snapshot_latest")
    args = ap.parse_args()

    rules_path = (ROOT / args.rules).resolve()
    candidates_path = (ROOT / args.candidates).resolve()
    out_prefix = (ROOT / args.out_prefix).resolve()

    rules_payload = _load_json(rules_path)
    candidates_payload = _load_json(candidates_path)
    rules = rules_payload.get("profiles") or {}
    candidates = candidates_payload.get("candidates") or []

    evaluated = [_evaluate_candidate(candidate, rules) for candidate in candidates]
    payload = {
      "generated_utc": _now_utc_iso(),
      "rules_path": str(rules_path),
      "candidates_path": str(candidates_path),
      "ready_ids": [item["id"] for item in evaluated if item["decision"] == "READY"],
      "blocked_ids": [item["id"] for item in evaluated if item["decision"] != "READY"],
      "candidates": evaluated
    }

    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    out_json = out_prefix.with_suffix(".json")
    out_txt = out_prefix.with_suffix(".txt")
    out_json.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    _write_text(out_txt, payload)

    print(f"battle snapshot built: {payload['generated_utc']}")
    print(f"ready={len(payload['ready_ids'])} blocked={len(payload['blocked_ids'])}")
    print(f"json={out_json}")
    print(f"txt={out_txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
