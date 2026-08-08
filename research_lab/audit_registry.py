#!/usr/bin/env python3
"""Build one durable, reviewable registry from all project-audit layers.

The registry is deliberately proposal-only.  It never edits strategy code,
configuration, risk or orders.  A finding becomes a repair task only after a
human marks it confirmed and reproduces it with the supplied verification.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "runtime" / "project_audit"
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
MANUAL_STATUSES = {"confirmed", "dismissed", "resolved"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def finding_id(source: str, rule: str, where: str, what: str) -> str:
    raw = f"{source}|{rule}|{where}|{what}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def _normalise(
    *,
    source: str,
    rule: str,
    where: str,
    what: str,
    why: str = "",
    how_to_verify: str = "",
    how_to_falsify: str = "",
    severity: str = "medium",
    status: str = "open",
    external_id: str = "",
) -> dict[str, Any]:
    severity = severity if severity in SEVERITY_RANK else "medium"
    item_id = finding_id(source, rule, where, what)
    return {
        "id": item_id,
        "external_id": external_id,
        "source": source,
        "rule": rule,
        "severity": severity,
        "status": status,
        "current": True,
        "where": where,
        "what": what,
        "why": why,
        "how_to_verify": how_to_verify,
        "how_to_falsify": how_to_falsify,
    }


def collect_continuous(root: Path = ROOT) -> list[dict[str, Any]]:
    payload = _read_json(root / "runtime" / "audit_ledger.json", {})
    noisy_rules = set(payload.get("noisy_rules") or [])
    rows: list[dict[str, Any]] = []
    for external_id, item in dict(payload.get("findings") or {}).items():
        raw_status = str(item.get("status") or "new")
        status = {
            "new": "open",
            "confirmed": "confirmed",
            "dismissed": "dismissed",
            "gone": "not_seen_latest",
        }.get(raw_status, raw_status)
        rule = str(item.get("rule") or "unknown")
        is_noisy = rule in noisy_rules and raw_status != "confirmed"
        if is_noisy and status == "open":
            status = "needs_triage"
        row = _normalise(
            source="continuous_static_liveness",
            rule=rule,
            where=str(item.get("where") or "unknown"),
            what=str(item.get("what") or "finding without summary"),
            why="deterministic static or liveness rule matched",
            how_to_verify="run the referenced strategy trace or inspect the cited branch",
            how_to_falsify=str(item.get("how_to_refute") or "reproduce and reject with evidence"),
            severity=(
                "info" if is_noisy
                else "high" if rule.startswith(("E1", "E2", "L1"))
                else "medium"
            ),
            status=status,
            external_id=str(external_id),
        )
        row["current"] = raw_status != "gone"
        rows.append(row)
    return rows


def _latest_ai_json(root: Path) -> Path | None:
    paths = sorted((root / "runtime" / "ai_audit").glob("*.json"))
    return paths[-1] if paths else None


def collect_ai(root: Path = ROOT) -> list[dict[str, Any]]:
    path = _latest_ai_json(root)
    if path is None:
        return []
    rows: list[dict[str, Any]] = []
    for item in list(_read_json(path, [])):
        rows.append(
            _normalise(
                source=f"ai_auditor:{item.get('source') or 'deterministic'}",
                rule=str(item.get("check") or "ai_review"),
                where=str(item.get("where") or "unknown"),
                what=str(item.get("what") or "finding without summary"),
                why=str(item.get("why") or ""),
                how_to_verify=str(item.get("how_to_verify") or ""),
                how_to_falsify=str(item.get("how_to_falsify") or ""),
                severity=str(item.get("severity") or "medium"),
                status="open" if str(item.get("status") or "new") == "new" else str(item.get("status")),
            )
        )
    return rows


def collect_technology_inventory(root: Path = ROOT) -> list[dict[str, Any]]:
    path = root / "runtime" / "ai_context" / "technology_registry.json"
    payload = _read_json(path, {})
    rows: list[dict[str, Any]] = []
    for item in list(payload.get("modules") or []):
        if item.get("inventory_status") != "tested_static_runtime_not_observed":
            continue
        test_refs = list(item.get("test_reference_files") or [])
        rows.append(
            _normalise(
                source="technology_inventory",
                rule="tested_static_runtime_not_observed",
                where=str(item.get("module") or "bot/unknown.py"),
                what="tested module is not statically reachable from the live monolith",
                why=(
                    "may be a research-only component, a dynamic import missed by the scanner, "
                    "or genuinely unwired code; static evidence alone is not a defect verdict"
                ),
                how_to_verify="trace imports and runtime call sites; then classify wire, keep research-only, or archive",
                how_to_falsify="show a runtime entry point or dynamic import that reaches the module",
                severity="info",
                status="needs_triage",
            )
        )
        rows[-1]["test_reference_count"] = len(test_refs)
        rows[-1]["purpose"] = str(item.get("purpose") or "")
    return rows


def merge_registry(
    current_rows: Iterable[dict[str, Any]],
    previous: dict[str, Any] | None = None,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    now = now or _now()
    previous = previous or {}
    prior_rows = {str(row.get("id")): row for row in list(previous.get("findings") or [])}
    merged: dict[str, dict[str, Any]] = {}

    for raw in current_rows:
        row = dict(raw)
        item_id = str(row["id"])
        prior = prior_rows.get(item_id, {})
        if str(prior.get("status")) in MANUAL_STATUSES:
            row["status"] = prior["status"]
            if prior.get("resolution_note"):
                row["resolution_note"] = prior["resolution_note"]
        row["first_seen_utc"] = prior.get("first_seen_utc") or now
        row["last_seen_utc"] = now
        row["occurrences"] = int(prior.get("occurrences") or 0) + 1
        row["current"] = bool(row.get("current", True))
        merged[item_id] = row

    for item_id, prior in prior_rows.items():
        if item_id in merged:
            continue
        row = dict(prior)
        row["current"] = False
        if str(row.get("status")) not in MANUAL_STATUSES:
            row["status"] = "not_seen_latest"
        merged[item_id] = row

    rows = sorted(
        merged.values(),
        key=lambda row: (
            not bool(row.get("current")),
            SEVERITY_RANK.get(str(row.get("severity")), 9),
            str(row.get("status")),
            str(row.get("id")),
        ),
    )
    current = [row for row in rows if row.get("current")]
    actionable = [
        row for row in current
        if row.get("status") in {"open", "confirmed"}
        and row.get("severity") in {"critical", "high", "medium"}
    ]
    return {
        "schema_id": "project_audit_registry_v1",
        "generated_at_utc": now,
        "authority": "proposal_only_no_automatic_live_mutation",
        "summary": {
            "total": len(rows),
            "current": len(current),
            "actionable": len(actionable),
            "inventory_needs_triage": sum(
                row.get("status") == "needs_triage" for row in current
            ),
            "confirmed": sum(row.get("status") == "confirmed" for row in rows),
            "dismissed": sum(row.get("status") == "dismissed" for row in rows),
            "model_candidates": sum(str(row.get("source", "")).endswith(":model") for row in current),
        },
        "findings": rows,
    }


def render_markdown(payload: dict[str, Any], *, limit: int = 60) -> str:
    summary = payload["summary"]
    lines = [
        "# Единый реестр аудита проекта",
        "",
        f"Обновлён: `{payload['generated_at_utc']}`",
        "",
        "Этот реестр ничего не исправляет автоматически и не имеет доступа к риску или ордерам.",
        "Находка становится задачей только после воспроизведения и статуса `confirmed`.",
        "",
        f"Всего: **{summary['total']}**; актуальных: **{summary['current']}**; "
        f"требуют разбора: **{summary['actionable']}**; инвентаризация подключения: "
        f"**{summary['inventory_needs_triage']}**; подтверждено: **{summary['confirmed']}**.",
        "",
        "| ID | Sev | Status | Source | Где | Что найдено |",
        "|---|---|---|---|---|---|",
    ]
    for row in list(payload.get("findings") or [])[:limit]:
        if not row.get("current"):
            continue
        clean = lambda value: str(value or "").replace("|", "/").replace("\n", " ")
        lines.append(
            f"| `{row['id']}` | {clean(row['severity'])} | {clean(row['status'])} | "
            f"{clean(row['source'])} | `{clean(row['where'])}` | {clean(row['what'])[:180]} |"
        )
    lines += [
        "",
        "## Работа со статусами",
        "",
        "```bash",
        "python3 research_lab/audit_registry.py --confirm <ID> --note 'evidence'",
        "python3 research_lab/audit_registry.py --dismiss <ID> --note 'false positive reason'",
        "python3 research_lab/audit_registry.py --resolve <ID> --note 'commit/test receipt'",
        "```",
        "",
    ]
    return "\n".join(lines)


def _write_csv(path: Path, findings: list[dict[str, Any]]) -> None:
    fields = [
        "id", "severity", "status", "current", "source", "rule", "where",
        "what", "why", "how_to_verify", "how_to_falsify", "first_seen_utc",
        "last_seen_utc", "occurrences", "resolution_note",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(findings)


def _set_status(path: Path, item_id: str, status: str, note: str) -> int:
    payload = _read_json(path, {})
    for row in list(payload.get("findings") or []):
        if str(row.get("id")) != item_id:
            continue
        row["status"] = status
        row["resolution_note"] = note
        row["status_updated_at_utc"] = _now()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{item_id}: {status}")
        return 0
    print(f"finding not found: {item_id}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--out-dir", default=str(DEFAULT_DIR))
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--confirm")
    action.add_argument("--dismiss")
    action.add_argument("--resolve")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    registry_path = out_dir / "registry.json"
    if args.confirm or args.dismiss or args.resolve:
        item_id = args.confirm or args.dismiss or args.resolve
        status = "confirmed" if args.confirm else "dismissed" if args.dismiss else "resolved"
        return _set_status(registry_path, str(item_id), status, args.note)

    current = collect_continuous(root) + collect_ai(root) + collect_technology_inventory(root)
    payload = merge_registry(current, _read_json(registry_path, {}))
    registry_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "registry.md").write_text(render_markdown(payload), encoding="utf-8")
    _write_csv(out_dir / "registry.csv", list(payload["findings"]))
    print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True))
    print(registry_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
