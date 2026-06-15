#!/usr/bin/env python3
"""Export a SAFE, structured snapshot of live server state into the repo.

Why: so the analyst/AI can read ground-truth live state from a committed file
(no manual copy-paste, no guessing). Codex runs this on the server and commits
the output; the next session reads reports/SERVER_SNAPSHOT_latest.{json,md}.

SAFETY (critical): secrets NEVER leave the server.
  * env is exported via an explicit ALLOWLIST of non-secret config keys only;
  * a recursive redactor masks any value whose key looks secret (defense in depth);
  * raw .env / API keys / tokens are never read into the output.

Pure stdlib. Read-only. Run:  python scripts/export_server_snapshot.py
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# --- secret redaction -------------------------------------------------------
_SECRET_RE = re.compile(
    r"(key|secret|token|passw|api|account|webhook|chat_id|chatid|seed|mnemonic|"
    r"private|credential|auth|signature|hmac)", re.IGNORECASE)


def _is_secret_key(k: str) -> bool:
    return bool(_SECRET_RE.search(str(k)))


def _is_allowed_non_secret_key_path(path: tuple[str, ...], k: str) -> bool:
    return bool(path and path[0] == "strategy_catalog" and k in {"active_keys", "key"})


def redact(obj, path: tuple[str, ...] = ()):
    """Recursively mask any value whose key looks like a secret."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key = str(k)
            if _is_secret_key(key) and not _is_allowed_non_secret_key_path(path, key):
                out[k] = "***REDACTED***"
            else:
                out[k] = redact(v, path + (key,))
        return out
    if isinstance(obj, list):
        return [redact(x, path) for x in obj]
    return obj


# --- safe env allowlist (non-secret strategy/risk config only) --------------
def _is_safe_config_key(k: str) -> bool:
    return (k.startswith("ENABLE_") or k.endswith("_RISK_MULT")
            or k.endswith("_MAX_OPEN_TRADES") or k in {
                "NO_ENTRY_HOURS_UTC", "RISK_PER_TRADE_PCT", "BYBIT_LEVERAGE",
                "MAX_POSITIONS", "DRY_RUN", "TRADE_ON", "DAILY_LOSS_LIMIT_PCT",
                "MAX_DRAWDOWN_PCT", "ORCH_GLOBAL_RISK_MULT", "MIN_NOTIONAL_USD"})


def _read_env_file() -> dict:
    """Parse .env (and active config env files) for SAFE keys only; never secrets."""
    found = {}
    for fn in [".env"] + sorted(glob.glob(str(ROOT / "configs" / "*canary*.env"))):
        path = ROOT / fn if not os.path.isabs(fn) else Path(fn)
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip(); v = v.split("#")[0].strip()
                if _is_secret_key(k) or not _is_safe_config_key(k):
                    continue
                found.setdefault(k, v)  # first wins (.env over canary)
        except Exception:
            continue
    return found


def safe_env() -> dict:
    """Only export explicitly-safe config keys; never secrets."""
    out = dict(_read_env_file())
    for k, v in os.environ.items():
        if _is_secret_key(k):
            continue
        if _is_safe_config_key(k):
            out[k] = v  # live process env overrides file
    return out


def load_json(path: Path):
    try:
        return redact(json.loads(path.read_text(encoding="utf-8", errors="ignore")))
    except Exception as e:
        return {"_error": str(e)}


def load_json_first(*paths: Path):
    for path in paths:
        if path.exists():
            return load_json(path)
    return {"_error": "not found", "paths": [str(p) for p in paths]}


def tail_jsonl(path: Path, n: int = 60):
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        rows = [json.loads(l) for l in lines[-n:] if l.strip()]
        return [redact(r) for r in rows]
    except Exception as e:
        return [{"_error": str(e)}]


def tail_jsonl_first(*paths: Path, n: int = 60):
    for path in paths:
        if path.exists():
            return tail_jsonl(path, n=n)
    return [{"_error": "not found", "paths": [str(p) for p in paths]}]


def build_snapshot() -> dict:
    rt = ROOT / "runtime"
    lm = rt / "live_mirror"
    snap = {
        "generated_at_utc": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "git_head": _git_head(),
        "safe_config": safe_env(),
        "heartbeat": load_json_first(rt / "bot_heartbeat.json", lm / "bot_heartbeat.json"),
        "regime": load_json_first(
            rt / "regime" / "orchestrator_state.json",
            lm / "regime" / "orchestrator_state.json",
        ),
        "live_positions": load_json_first(rt / "live_positions.json", lm / "live_positions.json"),
        "arb_roi_estimate": load_json_first(rt / "arb_roi_estimate.json", lm / "arb_roi_estimate.json"),
        "recent_trade_events": tail_jsonl_first(
            rt / "live_trade_events.jsonl",
            lm / "live_trade_events.jsonl",
            n=80,
        ),
    }
    # strategy catalog (config + TP/SL model) if importable
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        from bot.strategy_catalog import build_strategy_catalog
        snap["strategy_catalog"] = redact(
            build_strategy_catalog(),
            path=("strategy_catalog",),
        )
    except Exception as e:
        snap["strategy_catalog"] = {"_error": str(e)}
    # pnl by sleeve from the journal (best-effort)
    snap["pnl_by_sleeve"] = _pnl_by_sleeve(snap["recent_trade_events"])
    return snap


def _git_head() -> str:
    try:
        import subprocess
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=ROOT, text=True).strip()
    except Exception:
        return "?"


def _pnl_by_sleeve(events) -> dict:
    agg = {}
    for e in events:
        if (e.get("event") or e.get("type")) == "close":
            s = e.get("strategy") or "?"
            pnl = e.get("pnl") or e.get("realized_pnl") or 0.0
            try:
                pnl = float(pnl)
            except Exception:
                pnl = 0.0
            a = agg.setdefault(s, {"pnl": 0.0, "n": 0, "w": 0, "l": 0})
            a["pnl"] += pnl; a["n"] += 1
            a["w" if pnl > 0 else "l"] += 1
    return dict(sorted(agg.items(), key=lambda kv: kv[1]["pnl"]))


def to_markdown(snap: dict) -> str:
    L = [f"# Server snapshot — {snap['generated_at_utc']} (git {snap['git_head']})",
         "*Auto-exported, secrets redacted. Read this for ground-truth live state.*", ""]
    hb = snap.get("heartbeat", {})
    L += ["## Heartbeat",
          f"- open_trades={hb.get('open_trades')} trade_on={hb.get('trade_on')} "
          f"dry_run={hb.get('dry_run')} regime={hb.get('regime')}", ""]
    L += ["## Safe config (strategies / risk)"]
    for k, v in sorted(snap.get("safe_config", {}).items()):
        L.append(f"- {k} = {v}")
    L += ["", "## P&L by sleeve (from recent journal)"]
    for s, a in snap.get("pnl_by_sleeve", {}).items():
        L.append(f"- {s}: pnl={a['pnl']:+.4f} trades={a['n']} W/L={a['w']}/{a['l']}")
    cat = snap.get("strategy_catalog", {})
    L += ["", f"## Strategy catalog: active={cat.get('active_count')} "
          f"keys={','.join(cat.get('active_keys') or [])}"]
    L += ["", f"## Recent trade events: {len(snap.get('recent_trade_events', []))} (in JSON)"]
    return "\n".join(L)


def main():
    snap = build_snapshot()
    outdir = ROOT / "reports"
    outdir.mkdir(exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d_%H%M%S")
    (outdir / f"SERVER_SNAPSHOT_{stamp}.json").write_text(json.dumps(snap, indent=2, default=str))
    (outdir / "SERVER_SNAPSHOT_latest.json").write_text(json.dumps(snap, indent=2, default=str))
    (outdir / "SERVER_SNAPSHOT_latest.md").write_text(to_markdown(snap))
    print(f"wrote reports/SERVER_SNAPSHOT_latest.json + .md (git {snap['git_head']})")
    print(f"safe_config keys: {len(snap['safe_config'])} | "
          f"trade events: {len(snap['recent_trade_events'])} | "
          f"sleeves: {len(snap['pnl_by_sleeve'])}")


if __name__ == "__main__":
    main()
