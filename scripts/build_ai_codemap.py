#!/usr/bin/env python3
"""Generate an AI-facing map of the codebase: what exists and what it does.

Gives the on-board AI a "map of the territory" so it knows which files exist,
their purpose, and (for strategies) their classes — then it can use
bot.code_access.read_source(...) to read the exact file on demand instead of
being force-fed the whole monolith. Output: reports/AI_CODEMAP.md (+ .json).

Additive / read-only. Run:  python scripts/build_ai_codemap.py
"""
from __future__ import annotations

import ast
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRS = ("strategies", "bot", "backtest")


def _doc1(path: Path) -> str:
    try:
        mod = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        doc = ast.get_docstring(mod) or ""
        return doc.strip().splitlines()[0] if doc.strip() else ""
    except Exception:
        return ""


def _defs(path: Path):
    classes, funcs = [], []
    try:
        mod = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        for n in mod.body:
            if isinstance(n, ast.ClassDef):
                classes.append(n.name)
            elif isinstance(n, ast.FunctionDef):
                funcs.append(n.name)
    except Exception:
        pass
    return classes, funcs


def build() -> dict:
    out = {"generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "modules": {}}
    for d in DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.glob("*.py")):
            if p.name == "__init__.py":
                continue
            classes, funcs = _defs(p)
            out["modules"][str(p.relative_to(ROOT))] = {
                "purpose": _doc1(p),
                "classes": classes[:8],
                "functions": funcs[:10],
                "lines": sum(1 for _ in p.open(encoding="utf-8", errors="ignore")),
            }
    return out


def to_md(cm: dict) -> str:
    L = [f"# AI codemap — {cm['generated_at_utc']}",
         "*Map of strategy/bot modules. AI: use bot.code_access.read_source(path) to read any file.*", ""]
    cur = None
    for path, info in cm["modules"].items():
        top = path.split("/")[0]
        if top != cur:
            cur = top
            L.append(f"\n## {top}/")
        cls = (" | classes: " + ", ".join(info["classes"])) if info["classes"] else ""
        L.append(f"- `{path}` ({info['lines']}L): {info['purpose'] or '—'}{cls}")
    return "\n".join(L)


def main():
    cm = build()
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "AI_CODEMAP.json").write_text(json.dumps(cm, indent=2))
    (ROOT / "reports" / "AI_CODEMAP.md").write_text(to_md(cm))
    print(f"wrote reports/AI_CODEMAP.md ({len(cm['modules'])} modules)")


if __name__ == "__main__":
    main()
