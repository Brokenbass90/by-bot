#!/usr/bin/env python3
"""Build a conservative technology inventory for the onboard AI.

The inventory answers "what reusable modules exist?" without pretending that a
test-file mention proves production readiness.  Static import reachability is
reported as evidence only:

* ``direct_monolith_reference`` — imported/referenced by the live monolith;
* ``static_runtime_reachable`` — reachable through ``bot.*`` imports from it;
* ``test_reference_files`` — tests that mention the module;
* ``inventory_status`` — a deliberately non-promotional classification.

The script is read-only apart from its JSON output under
``runtime/ai_context``.  It never imports strategy modules, reads credentials,
or calls a broker.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "runtime" / "ai_context" / "technology_registry.json"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _tree(path: Path) -> ast.AST | None:
    try:
        return ast.parse(_read(path))
    except (SyntaxError, ValueError):
        return None


def _first_doc_line(path: Path) -> str:
    tree = _tree(path)
    doc = ast.get_docstring(tree) if tree is not None else ""
    for line in str(doc or "").splitlines():
        line = line.strip()
        if line:
            return line[:200]
    return ""


def _public_api(path: Path) -> list[str]:
    tree = _tree(path)
    if tree is None:
        return []
    names: list[str] = []
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
    return names[:10]


def _bot_imports(path: Path) -> set[str]:
    """Return statically visible ``bot.<module>`` dependencies."""
    tree = _tree(path)
    if tree is None:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("bot."):
                    out.add(alias.name.split(".", 2)[1])
        elif isinstance(node, ast.ImportFrom):
            if node.module == "bot":
                out.update(alias.name for alias in node.names)
            elif str(node.module or "").startswith("bot."):
                out.add(str(node.module).split(".", 2)[1])
    return out


def _reference_files(paths: Iterable[Path], name: str) -> list[Path]:
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    rows: list[Path] = []
    for path in paths:
        if pattern.search(_read(path)):
            rows.append(path)
    return rows


def _reachable(seed: set[str], graph: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    pending = list(seed)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        pending.extend(graph.get(name, set()) - seen)
    return seen


def build_registry(*, root: Path = ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    bot_dir = root / "bot"
    monolith = root / "smart_pump_reversal_bot.py"
    modules = {
        path.stem: path
        for path in sorted(bot_dir.glob("*.py"))
        if path.stem != "__init__"
    }
    graph = {
        name: {dep for dep in _bot_imports(path) if dep in modules}
        for name, path in modules.items()
    }
    direct = {name for name in _bot_imports(monolith) if name in modules}
    # Some legacy live wiring uses module-qualified calls without a normal
    # import. Keep this as a static reference, not proof of execution.
    monolith_text = _read(monolith)
    direct.update(
        name for name in modules
        if re.search(rf"\bbot\.{re.escape(name)}\b", monolith_text)
    )
    reachable = _reachable(direct, graph)
    test_paths = sorted((root / "tests").glob("test_*.py"))
    runtime_paths = [monolith]
    for folder in ("scripts", "web"):
        runtime_paths.extend(sorted((root / folder).rglob("*.py")))

    rows: list[dict[str, Any]] = []
    for name, path in modules.items():
        test_refs = _reference_files(test_paths, name)
        runtime_refs = _reference_files(runtime_paths, name)
        is_direct = name in direct
        is_reachable = name in reachable
        if is_reachable:
            status = "static_runtime_reachable"
        elif test_refs:
            status = "tested_static_runtime_not_observed"
        else:
            status = "inventory_only"
        rows.append(
            {
                "module": f"bot/{path.name}",
                "name": name,
                "purpose": _first_doc_line(path),
                "public_api": _public_api(path),
                "direct_monolith_reference": is_direct,
                "static_runtime_reachable": is_reachable,
                "runtime_reference_files": [
                    str(ref.relative_to(root)) for ref in runtime_refs[:12]
                ],
                "test_reference_files": [
                    str(ref.relative_to(root)) for ref in test_refs[:12]
                ],
                "inventory_status": status,
                "lines": len(_read(path).splitlines()),
            }
        )

    status_counts: dict[str, int] = {}
    for row in rows:
        key = str(row["inventory_status"])
        status_counts[key] = status_counts.get(key, 0) + 1
    tested_not_observed = sorted(
        (
            row for row in rows
            if row["inventory_status"] == "tested_static_runtime_not_observed"
            and row["purpose"]
        ),
        key=lambda row: (-len(row["test_reference_files"]), row["name"]),
    )
    return {
        "schema_id": "technology_inventory_v2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "authority": "static_inventory_not_promotion_evidence",
        "method": {
            "runtime_seed": "smart_pump_reversal_bot.py static bot imports/references",
            "reachability": "transitive static bot import graph",
            "test_coverage_proxy": "test filename mention only; not behavioral readiness",
        },
        "warnings": [
            "Static reachability does not prove that a branch executes.",
            "A test-file reference does not prove strategy quality, live parity, or promotion readiness.",
            "Dynamic imports and runtime monkey-patching may be absent from this inventory.",
        ],
        "totals": {
            "modules": len(rows),
            "direct_monolith_reference": len(direct),
            "static_runtime_reachable": len(reachable),
            "tested_static_runtime_not_observed": len(tested_not_observed),
        },
        "status_counts": dict(sorted(status_counts.items())),
        "tested_static_runtime_not_observed": [
            {
                "name": row["name"],
                "purpose": row["purpose"],
                "test_reference_count": len(row["test_reference_files"]),
            }
            for row in tested_not_observed[:40]
        ],
        "modules": rows,
    }


def _one_line(text: str, width: int = 110) -> str:
    """Purpose docstrings are multi-line; the operator context needs one line."""
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= width else flat[: width - 1] + "\u2026"


def compact_registry(payload: dict[str, Any], *, limit: int = 24) -> dict[str, Any]:
    """Shrink the registry for the operator context WITHOUT hiding module names.

    Before 2026-08-11 this returned counts plus at most ``limit`` unwired
    modules. The operator could therefore read "74 modules built and not
    wired" and name only 24 of them, and could name none of the 45 modules
    that ARE wired. Asking it "what could improve this leg" was answerable
    only for a third of the inventory it was supposedly reporting on.

    The registry costs about 4 KB inside a 438 KB context. Truncation was
    saving nothing that mattered and was removing the half of the answer the
    question depended on. Both halves are now listed by name and purpose;
    ``limit`` still bounds the legacy field so existing callers and tests keep
    their contract.
    """
    modules = payload.get("modules")
    modules = modules if isinstance(modules, list) else []

    def _catalog(rows: list, *, cap: int, width: int = 46) -> list[dict[str, Any]]:
        out = []
        for row in rows[: max(0, int(cap))]:
            if not isinstance(row, dict):
                continue
            # "lines" \u0434\u0440\u043e\u043f\u043d\u0443\u0442\u043e: \u0440\u0430\u0437\u043c\u0435\u0440 \u043d\u0435 \u0433\u043e\u0432\u043e\u0440\u0438\u0442 \u043e \u043f\u043e\u043b\u044c\u0437\u0435, \u0430 \u0431\u044e\u0434\u0436\u0435\u0442 \u0435\u0441\u0442.
            out.append({
                "name": row.get("name"),
                "purpose": _one_line(row.get("purpose"), width=width),
                "tests": len(row.get("test_reference_files") or []),
            })
        return out

    unwired = [
        r for r in modules
        if isinstance(r, dict) and not r.get("static_runtime_reachable")
    ]
    wired = [
        r for r in modules
        if isinstance(r, dict) and r.get("static_runtime_reachable")
    ]
    # Tested first, then largest: a module with tests is closest to usable,
    # and size is a crude proxy for how much work already exists in it.
    unwired.sort(key=lambda r: (-len(r.get("test_reference_files") or []),
                                -int(r.get("lines") or 0)))
    wired.sort(key=lambda r: str(r.get("name") or ""))

    return {
        "schema_id": payload.get("schema_id"),
        "generated_at_utc": payload.get("generated_at_utc"),
        "authority": payload.get("authority"),
        "totals": payload.get("totals") or {},
        "warnings": list(payload.get("warnings") or []),
        "tested_static_runtime_not_observed": list(
            payload.get("tested_static_runtime_not_observed") or []
        )[: max(0, int(limit))],
        "reading_guide": (
            "not_wired = \u0441\u0431\u043e\u0440\u043a\u0430 \u0435\u0441\u0442\u044c, \u0432 \u0436\u0438\u0432\u043e\u043c \u043f\u0443\u0442\u0438 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430. "
            "\u042d\u0442\u043e \u0441\u0442\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0444\u0430\u043a\u0442 \u043e \u0441\u0441\u044b\u043b\u043a\u0430\u0445, \u0430 \u043d\u0435 \u0434\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u044c\u0441\u0442\u0432\u043e \u043f\u043e\u043b\u044c\u0437\u044b: "
            "\u043f\u0440\u0435\u0434\u043b\u0430\u0433\u0430\u0442\u044c \u043c\u043e\u0434\u0443\u043b\u044c \u043c\u043e\u0436\u043d\u043e, \u0443\u0442\u0432\u0435\u0440\u0436\u0434\u0430\u0442\u044c \u0435\u0433\u043e \u044d\u0444\u0444\u0435\u043a\u0442 \u2014 \u043d\u0435\u043b\u044c\u0437\u044f."
        ),
        "not_wired_catalog": _catalog(unwired, cap=90),
        "wired_names": [r.get("name") for r in wired][:60],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    out = Path(args.out).resolve()
    allowed = root / "runtime" / "ai_context"
    try:
        out.relative_to(allowed)
    except ValueError:
        raise SystemExit(f"--out must be under {allowed}")
    payload = build_registry(root=root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not args.quiet:
        totals = payload["totals"]
        print(json.dumps(totals, ensure_ascii=False, sort_keys=True))
        print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
