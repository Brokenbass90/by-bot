"""Safe, read-only code access for the on-board AI ("open its eyes" to the code).

The AI can already see strategy CONFIG + TP/SL model (bot.strategy_catalog) and
live STATE (server snapshot). This module is the next step: let it read the
actual SOURCE of strategies and bot modules on demand — without dumping the
whole 14.7k-line monolith and without ever leaking secrets.

Design / safety (this is the security boundary, so it is strict):
  * read-only; no write/exec;
  * only files INSIDE the repo and inside an allowlisted code/config dir;
  * `..` path escape is rejected; symlinks resolved and re-checked;
  * `.env*` and secret-looking filenames are refused outright;
  * line-level redaction masks any `KEY = secret`-style assignment as defense
    in depth (code should not contain secrets, but never assume);
  * hard size cap so a single call can't return a huge blob.

Intended use: Codex wires `read_source` / `list_sources` / `grep_sources` as
on-board-AI tools (Telegram + web). Pure stdlib.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_DIRS = ("strategies", "bot", "backtest", "scripts", "web", "tests")
MAX_BYTES = 200_000

_DENY_NAME = re.compile(
    r"(^\.env|\.env$|\.env\.|secret|credential|web_config|exchange_keys|"
    r"\.key$|\.pem$|id_rsa)",
    re.IGNORECASE,
)
_SECRET_LINE = re.compile(
    r"^\s*[\"']?[\w\.\-]*(key|secret|token|passw|api|account|webhook|chat_id|hmac|private)"
    r"[\w\.\-]*[\"']?\s*[:=]", re.IGNORECASE)


class CodeAccessError(Exception):
    pass


def _safe_resolve(relpath: str) -> Path:
    if not relpath or relpath.startswith(("/", "~")) or ".." in Path(relpath).parts:
        raise CodeAccessError(f"rejected path: {relpath}")
    target = (ROOT / relpath).resolve()
    try:
        rel = target.relative_to(ROOT)
    except ValueError:
        raise CodeAccessError("path escapes repo root")
    if not rel.parts or rel.parts[0] not in ALLOWED_DIRS:
        raise CodeAccessError(f"dir not allowed (must be one of {ALLOWED_DIRS})")
    if _DENY_NAME.search(target.name):
        raise CodeAccessError("secret-like file refused")
    return target


def _redact(text: str) -> str:
    out = []
    for line in text.splitlines():
        if _SECRET_LINE.match(line):
            k = re.split(r"[:=]", line, maxsplit=1)[0]
            out.append(f"{k}= ***REDACTED***")
        else:
            out.append(line)
    return "\n".join(out)


def read_source(relpath: str, max_bytes: int = MAX_BYTES) -> str:
    """Return the (secret-redacted) text of a single repo source file."""
    target = _safe_resolve(relpath)
    if not target.is_file():
        raise CodeAccessError(f"not a file: {relpath}")
    if target.stat().st_size > max_bytes:
        data = target.read_text(encoding="utf-8", errors="ignore")[:max_bytes]
        return _redact(data) + f"\n... [truncated at {max_bytes} bytes]"
    return _redact(target.read_text(encoding="utf-8", errors="ignore"))


def list_sources(subdir: str = "strategies") -> List[str]:
    """List code files in an allowlisted dir (relative paths)."""
    base = _safe_resolve(subdir)
    if not base.is_dir():
        raise CodeAccessError(f"not a dir: {subdir}")
    out = []
    for p in sorted(base.rglob("*")):
        if p.is_file() and p.suffix in (".py", ".json", ".env", ".md") and not _DENY_NAME.search(p.name):
            out.append(str(p.relative_to(ROOT)))
    return out


def grep_sources(pattern: str, subdir: str = "strategies", max_hits: int = 60) -> List[str]:
    """Find `pattern` in code; returns 'relpath:lineno: line' (redacted)."""
    rx = re.compile(pattern)
    hits: List[str] = []
    base = _safe_resolve(subdir)
    for p in sorted(base.rglob("*.py")):
        if _DENY_NAME.search(p.name):
            continue
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if rx.search(line):
                    safe = "***REDACTED***" if _SECRET_LINE.match(line) else line.strip()
                    hits.append(f"{p.relative_to(ROOT)}:{i}: {safe}")
                    if len(hits) >= max_hits:
                        return hits
        except Exception:
            continue
    return hits
