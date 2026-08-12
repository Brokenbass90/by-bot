#!/usr/bin/env python3
"""Build a non-destructive evidence map for code in a dirty workbench."""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CODE_ROOTS = {"backtest", "bot", "forex", "research_lab", "scripts", "strategies", "web"}
CODE_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".html", ".css", ".sh"}
TEXT_SUFFIXES = CODE_SUFFIXES | {".md", ".json", ".yaml", ".yml", ".toml"}
BULK_ROOTS = {"data", "logs", "runtime", ".git", ".venv", "node_modules"}
REFERENCE_INVENTORY_MARKERS = (
    "dirty_research_workbench_audit", "repo_drift_manifest", "project_canonical_index",
    "project_map",
)
ORDER_AUTHORITY_PATTERNS = (
    re.compile(r"/v5/order/", re.IGNORECASE),
    re.compile(r"\b(?:place_order|submit_order|cancel_order|set_trading_stop)\s*\(", re.IGNORECASE),
)
CREDENTIAL_PATTERNS = (
    re.compile(r"\b(?:api_secret|private_api|bybit_accounts_json|alpaca_api_secret)\b", re.IGNORECASE),
)


def _status_records(root: Path) -> list[tuple[str, str]]:
    raw = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=root
    )
    fields = raw.split(b"\0")
    out: list[tuple[str, str]] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        if not field:
            index += 1
            continue
        text = field.decode("utf-8", errors="surrogateescape")
        status, path = text[:2], text[3:]
        out.append((status, path))
        index += 2 if any(char in status for char in "RC") else 1
    return out


def _candidate_paths(root: Path) -> list[tuple[str, Path]]:
    rows = []
    for status, raw in _status_records(root):
        path = Path(raw)
        if path.parts and path.parts[0] in CODE_ROOTS and path.suffix.lower() in CODE_SUFFIXES:
            if (root / path).is_file():
                rows.append((status, path))
    return rows


def _corpus(root: Path) -> dict[Path, str]:
    rows: dict[Path, str] = {}
    for current, directories, filenames in os.walk(root):
        directories[:] = [name for name in directories if name not in BULK_ROOTS]
        base = Path(current)
        for name in filenames:
            path = base / name
            rel = path.relative_to(root)
            if any(marker in rel.as_posix().lower() for marker in REFERENCE_INVENTORY_MARKERS):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 2_000_000:
                continue
            try:
                rows[rel] = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
    return rows


def _risk_flags(path: Path, text: str, tree: ast.AST | None) -> tuple[bool, bool]:
    if path.suffix == ".py" and tree is not None:
        call_names = set()
        identifiers = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                identifiers.add(node.id.lower())
            elif isinstance(node, ast.Attribute):
                identifiers.add(node.attr.lower())
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    call_names.add(func.id.lower())
                elif isinstance(func, ast.Attribute):
                    call_names.add(func.attr.lower())
        order = bool(call_names & {"place_order", "submit_order", "cancel_order", "set_trading_stop"})
        credential = bool(identifiers & {"api_secret", "private_api", "bybit_accounts_json", "alpaca_api_secret"})
        return order, credential
    return (
        any(pattern.search(text) for pattern in ORDER_AUTHORITY_PATTERNS),
        any(pattern.search(text) for pattern in CREDENTIAL_PATTERNS),
    )


def classify_candidate(*, syntax_ok: bool | None, test_refs: int, prereg_refs: int,
                       evidence_refs: int, other_refs: int) -> str:
    if syntax_ok is False:
        return "broken_code"
    if test_refs:
        return "test_backed_candidate"
    if prereg_refs or evidence_refs:
        return "evidence_backed_needs_reproduction"
    if other_refs:
        return "referenced_needs_review"
    return "unreferenced_quarantine_candidate"


def analyze(root: Path) -> dict[str, Any]:
    root = root.resolve()
    corpus = _corpus(root)
    candidate_rows = _candidate_paths(root)
    candidate_stems = {path.stem for _, path in candidate_rows}
    refs_by_stem: dict[str, set[Path]] = {stem: set() for stem in candidate_stems}
    identifier = re.compile(r"[A-Za-z0-9_]+")
    for source, source_text in corpus.items():
        present = (set(identifier.findall(source_text)) | set(identifier.findall(source.as_posix()))) & candidate_stems
        for stem in present:
            refs_by_stem[stem].add(source)
    candidates = []
    for status, rel in candidate_rows:
        path = root / rel
        text = path.read_text(encoding="utf-8", errors="ignore")
        syntax_ok: bool | None = None
        syntax_error = None
        has_docstring = False
        tree: ast.AST | None = None
        if path.suffix == ".py":
            try:
                tree = ast.parse(text)
                syntax_ok = True
                has_docstring = bool(ast.get_docstring(tree))
            except SyntaxError as exc:
                syntax_ok = False
                syntax_error = f"line {exc.lineno}: {exc.msg}"
        stem = path.stem
        rel_text = rel.as_posix()
        references = sorted(refs_by_stem.get(stem, set()) - {rel})
        tests = sorted(str(item) for item in references if item.parts and item.parts[0] == "tests")
        prereg = sorted(str(item) for item in references if "prereg" in item.parts)
        evidence = sorted(
            str(item) for item in references
            if item.parts and item.parts[0] in {"reports", "research_lab"}
            and ("results" in item.parts or item.parts[0] == "reports")
        )
        other = sorted(set(str(item) for item in references) - set(tests) - set(prereg) - set(evidence))
        category = classify_candidate(
            syntax_ok=syntax_ok, test_refs=len(tests), prereg_refs=len(prereg),
            evidence_refs=len(evidence), other_refs=len(other),
        )
        score = min(20, len(tests) * 6) + min(12, len(prereg) * 4) + min(12, len(evidence) * 2)
        score += min(5, len(other)) + int(has_docstring) + int('__name__ == "__main__"' in text)
        possible_order_authority, possible_credential_touch = _risk_flags(path, text, tree)
        candidates.append({
            "path": rel_text,
            "git_status": status,
            "bytes": path.stat().st_size,
            "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "syntax_ok": syntax_ok,
            "syntax_error": syntax_error,
            "has_module_docstring": has_docstring,
            "has_main_guard": '__name__ == "__main__"' in text,
            "possible_order_authority": possible_order_authority,
            "possible_credential_touch": possible_credential_touch,
            "test_refs": tests[:20],
            "prereg_refs": prereg[:20],
            "evidence_refs": evidence[:30],
            "other_refs": other[:20],
            "reference_counts": {
                "tests": len(tests), "prereg": len(prereg),
                "evidence": len(evidence), "other": len(other),
            },
            "category": category,
            "priority_score": score,
            "recommended_action": {
                "test_backed_candidate": "scope-review and run focused tests; commit separately if reproducible",
                "evidence_backed_needs_reproduction": "bind to prereg/passport and reproduce before adoption",
                "referenced_needs_review": "trace callers and compare with canonical implementation",
                "unreferenced_quarantine_candidate": "preserve outside active tree; delete only after owner review",
                "broken_code": "do not run; repair only if references justify it",
            }[category],
        })
    candidates.sort(key=lambda item: (-item["priority_score"], item["path"]))
    counts = Counter(item["category"] for item in candidates)
    return {
        "schema_id": "dirty_research_workbench_audit_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "read_only_analysis": True,
        "deleted_or_moved": 0,
        "candidate_count": len(candidates),
        "category_counts": dict(sorted(counts.items())),
        "possible_order_authority_count": sum(item["possible_order_authority"] for item in candidates),
        "possible_credential_touch_count": sum(item["possible_credential_touch"] for item in candidates),
        "candidates": candidates,
    }


def render_markdown(result: dict[str, Any]) -> str:
    counts = result["category_counts"]
    lines = [
        "# Аудит грязной исследовательской рабочей области",
        "",
        f"Проверено code-кандидатов: **{result['candidate_count']}**. Ничего не удалено и не перемещено.",
        "",
        "## Сводка",
        "",
        "| категория | количество |",
        "|---|---:|",
    ]
    for key, value in counts.items():
        lines.append(f"| `{key}` | {value} |")
    lines += ["", "## Первая очередь разбора", "", "| score | категория | путь | tests | evidence | live-risk |", "|---:|---|---|---:|---:|---|"]
    for row in result["candidates"][:50]:
        refs = row["reference_counts"]
        lines.append(
            f"| {row['priority_score']} | `{row['category']}` | `{row['path']}` | "
            f"{refs['tests']} | {refs['evidence'] + refs['prereg']} | "
            f"{'yes' if row['possible_order_authority'] else 'no'} |"
        )
    broken = [row for row in result["candidates"] if row["category"] == "broken_code"]
    if broken:
        lines += ["", "## Синтаксически сломано", ""]
        lines += [f"- `{row['path']}` — {row['syntax_error']}" for row in broken]
    lines += [
        "", "## Правило зачистки", "",
        "Сначала воспроизводимость и reference-map, затем отдельный commit или карантин. "
        "Массовое удаление по возрасту/имени запрещено.", "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    args = parser.parse_args()
    result = analyze(args.root)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({
        "candidate_count": result["candidate_count"],
        "category_counts": result["category_counts"],
        "possible_order_authority_count": result["possible_order_authority_count"],
        "possible_credential_touch_count": result["possible_credential_touch_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
