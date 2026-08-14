#!/usr/bin/env python3
"""Fail-closed intake from AI proposals to the human research-review queue.

This program has no network, broker, live, promotion, or experiment-launch
authority.  It accepts only complete, falsifiable research cards, checks them
against closed-hypothesis memory, deduplicates them, and writes proposal-only
queue entries requiring explicit owner approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.hypothesis_memory import HypothesisMemory


REQUIRED_TEXT = ("description", "rationale", "mechanism", "cost_model", "test_contract", "death_criteria", "risk_note", "acceptance_gate")
REQUIRED_LISTS = ("data_required", "source_ids")
ALLOWED_TYPES = {"new_strategy_idea", "new_sweep"}
STRATEGY_SCOPED_CLOSED_PREFIXES = {"att1"}


def _matches_target_scope(key: str, target_strategy: Any) -> bool:
    prefix = str(key or "").split("_", 1)[0].lower()
    if prefix not in STRATEGY_SCOPED_CLOSED_PREFIXES:
        return True
    return prefix in str(target_strategy or "").lower()


def _stable_key(card: dict[str, Any]) -> str:
    identity = {
        "type": card.get("type"),
        "target_strategy": card.get("target_strategy"),
        "mechanism": card.get("mechanism"),
        "test_contract": card.get("test_contract"),
    }
    raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def normalize_card(raw: Any, memory: HypothesisMemory) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return None, ["proposal_not_object"]
    if raw.get("type") not in ALLOWED_TYPES:
        errors.append("unsupported_type")
    for field in REQUIRED_TEXT:
        if not isinstance(raw.get(field), str) or not raw[field].strip():
            errors.append(f"missing_{field}")
    for field in REQUIRED_LISTS:
        values = raw.get(field)
        if not isinstance(values, list) or not values or not all(isinstance(value, str) and value.strip() for value in values):
            errors.append(f"missing_{field}")
    if errors:
        return None, errors

    card = {field: raw.get(field) for field in ("type", "target_strategy", *REQUIRED_TEXT, *REQUIRED_LISTS)}
    card["data_required"] = [value.strip()[:300] for value in card["data_required"][:20]]
    card["source_ids"] = [value.strip()[:120] for value in card["source_ids"][:20]]
    card["proposal_key"] = _stable_key(card)
    query = f"{card['description']} {card['mechanism']} {card.get('target_strategy') or ''}"
    closed = [
        item for item in memory.check(query)
        if _matches_target_scope(item.key, card.get("target_strategy"))
    ]
    card["closed_hypothesis_matches"] = [
        {"key": item.key, "verdict": item.verdict, "mechanism": item.mechanism, "reopen_if": item.reopen_if, "evidence": item.evidence}
        for item in closed[:5]
    ]
    card["status"] = "quarantined_closed_match" if closed else "awaiting_owner_approval"
    card["authority"] = "proposal_only_no_experiment_or_live_authority"
    card["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    return card, []


def _read_existing_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("proposal_key"):
            keys.add(str(value["proposal_key"]))
    return keys


def ingest(entries: Iterable[Any], *, memory: HypothesisMemory, existing_keys: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen = set(existing_keys)
    for index, raw in enumerate(entries):
        card, errors = normalize_card(raw, memory)
        if card is None:
            rejected.append({"index": index, "errors": errors})
            continue
        if card["proposal_key"] in seen:
            rejected.append({"index": index, "errors": ["duplicate_proposal_key"], "proposal_key": card["proposal_key"]})
            continue
        seen.add(card["proposal_key"])
        accepted.append(card)
    return accepted, rejected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="One market_scanner JSONL file")
    parser.add_argument("--output", default="runtime/research/idea_intake_queue.jsonl", type=Path)
    parser.add_argument("--rejects", default="runtime/research/idea_intake_rejects.json", type=Path)
    args = parser.parse_args()

    proposals: list[Any] = []
    for line in args.input.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ai = row.get("ai_proposals") if isinstance(row, dict) else None
        if isinstance(ai, dict) and isinstance(ai.get("proposals"), list):
            proposals.extend(ai["proposals"])

    accepted, rejected = ingest(
        proposals,
        memory=HypothesisMemory(),
        existing_keys=_read_existing_keys(args.output),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if accepted:
        with args.output.open("a", encoding="utf-8") as handle:
            for card in accepted:
                handle.write(json.dumps(card, ensure_ascii=False, sort_keys=True) + "\n")
    args.rejects.parent.mkdir(parents=True, exist_ok=True)
    args.rejects.write_text(json.dumps({"accepted": len(accepted), "rejected": rejected}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": len(accepted), "rejected": len(rejected), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
