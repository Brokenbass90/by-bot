# -*- coding: utf-8 -*-
"""Static guards for fail-closed web actions and configuration defaults."""
from pathlib import Path


ROOT = Path(__file__).resolve().parent
app = (ROOT / "app.py").read_text(encoding="utf-8")
config = (ROOT / "config.py").read_text(encoding="utf-8")
pipeline = (ROOT / "pipeline.py").read_text(encoding="utf-8")
journal = (ROOT / "journal.py").read_text(encoding="utf-8")

assert 'EXECUTION_ENABLE = _flag("SIGCOPY_EXECUTION_ENABLE", "0")' in config
assert 'ALLOWED_ACCOUNT_LOGINS = _ints("SIGCOPY_ALLOWED_ACCOUNT_LOGINS", ())' in config
assert "ALLOW_LIVE             = False" in config
assert 'os.getenv("SIGCOPY_MT5_TOKEN", "")' in config

assert '@app.post("/api/action/prepare")' in app
assert '@app.post("/api/action/execute")' in app
assert "прямое закрытие отключено" in app
assert "прямой безубыток отключён" in app
assert "approvedAction('close'" in app
assert "approvedAction('breakeven'" in app

assert 'if use_llm and (p.kind == "UNKNOWN" or (p.kind == "SIGNAL" and p.errors)):' in pipeline
assert "if hist is None:\n            continue" in journal
assert 'source = "последний слепок"' not in journal

print("OK: signal-copy web actions, config, LLM fallback, and journal fail closed")
