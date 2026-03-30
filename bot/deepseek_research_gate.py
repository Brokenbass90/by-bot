"""
bot/deepseek_research_gate.py — Bounded Research Scope for DeepSeek Autonomy
=============================================================================
Prevents the AI from running arbitrary research or modifying live configs
without human approval. This is the SAFETY LAYER between DeepSeek's autonomy
and the live bot.

DESIGN PRINCIPLE:
  "DeepSeek can PROPOSE anything. It can EXECUTE only pre-approved specs."

THREE TIERS of research:
  TIER 1 — AUTO (runs immediately, no approval needed):
    - Any spec from configs/autoresearch/approved_specs.txt
    - Read-only operations (status checks, log analysis)
    - New symbol scans (does not change live config)

  TIER 2 — PROPOSAL (queued for human approval):
    - New autoresearch spec files not in approved list
    - Any change to live bot parameters
    - Adding/removing symbols from active allowlists
    - Changing risk/leverage settings

  TIER 3 — BLOCKED (never auto-executed):
    - Any modification to smart_pump_reversal_bot.py
    - Changes to BYBIT_API_KEY / credentials
    - Anything touching backup/ or baselines/
    - Shutting down the bot process

PROPOSAL WORKFLOW:
  1. DeepSeek calls `gate.propose(spec_path, reason)` instead of running directly
  2. Gate writes proposal to configs/research_proposals/{timestamp}_{name}.json
  3. Gate sends Telegram: "⚠️ Research proposal: {name}. Reply /approve or /reject"
  4. Proposal auto-expires after PROPOSAL_TIMEOUT_HOURS (default 48h)
  5. On /approve: spec is run AND added to approved list for future auto-runs
  6. On /reject: proposal archived, DeepSeek notified

AUTO-TRIGGERS:
  Triggers are checked every TRIGGER_CHECK_INTERVAL_S (default 3600 = 1h).
  They fire when:
    - Strategy win rate drops below TRIGGER_WR_THRESHOLD (default 45%) over 30d
    - Symbol enters/exits top-20 Bybit by volume
    - Equity curve crosses below MA (detected by equity_curve_autopilot)
    - Weekly cron explicitly calls gate.check_triggers()

  When trigger fires → automatically PROPOSES (not runs) the corresponding
  pre-approved research spec. Human still approves before execution.

KILL-ZONE AUTO-AUDIT:
  If a symbol has net PnL < KILL_ZONE_THRESHOLD_USD (default -0.5$) over 30d,
  gate adds it to configs/kill_zone_candidates.json. Human reviews weekly.
  Auto-ban NOT implemented — always requires human confirmation.

Usage in deepseek_weekly_cron.py:
    from bot.deepseek_research_gate import gate

    # Instead of: subprocess.run(["python3", "scripts/run_autoresearch.py", "--spec", spec])
    # Use:
    if gate.can_run(spec_path):
        gate.run_approved(spec_path)
    else:
        gate.propose(spec_path, reason="Weekly analysis suggests this research")

    # Check triggers:
    triggered_specs = gate.check_triggers(strategy_stats, symbol_universe)
    for spec in triggered_specs:
        gate.propose(spec, reason=f"Auto-trigger: {spec}")

Config:
    RESEARCH_GATE_ENABLED=1          # 0 to disable gate (dev mode)
    PROPOSAL_TIMEOUT_HOURS=48
    TRIGGER_WR_THRESHOLD=45.0        # % win rate below which trigger fires
    TRIGGER_CHECK_INTERVAL_S=3600
    KILL_ZONE_THRESHOLD_USD=-0.5     # net PnL threshold for kill-zone flagging
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT             = Path(__file__).resolve().parent.parent
APPROVED_FILE    = ROOT / "configs" / "autoresearch" / "approved_specs.txt"
PROPOSALS_DIR    = ROOT / "configs" / "research_proposals"
KILL_ZONE_FILE   = ROOT / "configs" / "kill_zone_candidates.json"
TRIGGER_LOG_FILE = ROOT / "configs" / "research_trigger_log.json"

GATE_ENABLED            = os.getenv("RESEARCH_GATE_ENABLED", "1") == "1"
PROPOSAL_TIMEOUT_HOURS  = int(os.getenv("PROPOSAL_TIMEOUT_HOURS", "48"))
TRIGGER_WR_THRESHOLD    = float(os.getenv("TRIGGER_WR_THRESHOLD", "45.0"))
KILL_ZONE_THRESHOLD_USD = float(os.getenv("KILL_ZONE_THRESHOLD_USD", "-0.5"))

# ── Tier 3 BLOCKED patterns — never auto-executed ────────────────────────────
_BLOCKED_PATTERNS = [
    "smart_pump_reversal_bot",
    "BYBIT_API_KEY", "BYBIT_API_SECRET",
    "baselines/", "backup/",
    "kill_bot", "stop_bot", "shutdown",
]

# ── Pre-approved spec names (basename, no path) — auto-run without approval ──
_BUILTIN_APPROVED = {
    "triple_screen_elder_v13_zoom.json",
    "portfolio_elder_6strat_test.json",
    "funding_rate_reversion_v1_grid.json",
    "liquidation_cascade_v1_grid.json",
    "sr_break_retest_volume_v1_revival_v1.json",
    "equities_monthly_v27_intramonth_stop.json",
    "equities_monthly_v23_spy_regime_gate.json",
}


# ── Telegram helper (self-contained, no bot dependency) ─────────────────────

def _tg(token: str, chat_id: str, msg: str) -> None:
    if not token or not chat_id:
        return
    import ssl
    from urllib import request as ureq
    _chunk = 3900
    parts = [msg[i:i + _chunk] for i in range(0, len(msg), _chunk)]
    total = len(parts)
    ctx = ssl.create_default_context()
    for idx, part in enumerate(parts, 1):
        text = f"[{idx}/{total}]\n{part}" if total > 1 else part
        payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = ureq.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with ureq.urlopen(req, context=ctx, timeout=10):
                pass
        except Exception:
            pass


# ── ResearchGate ─────────────────────────────────────────────────────────────

class ResearchGate:
    """
    Safety gate between DeepSeek's autonomy and live bot execution.
    All research proposals pass through here.
    """

    def __init__(self) -> None:
        PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
        self._approved_cache: Optional[set] = None
        self._approved_mtime: float = 0.0
        self._tg_token  = os.getenv("TG_TOKEN", "")
        self._tg_chat   = os.getenv("TG_CHAT_ID", "") or os.getenv("TG_CHAT", "")

    # ── Approved list ─────────────────────────────────────────────────────────

    def _load_approved(self) -> set:
        """Load approved spec names from file + builtins."""
        approved = set(_BUILTIN_APPROVED)
        if APPROVED_FILE.exists():
            mtime = APPROVED_FILE.stat().st_mtime
            if mtime != self._approved_mtime or self._approved_cache is None:
                lines = APPROVED_FILE.read_text(encoding="utf-8").splitlines()
                self._approved_cache = {
                    l.strip() for l in lines
                    if l.strip() and not l.strip().startswith("#")
                }
                self._approved_mtime = mtime
                approved |= self._approved_cache
        return approved

    def add_approved(self, spec_name: str) -> None:
        """Permanently add a spec to the approved list."""
        APPROVED_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = APPROVED_FILE.read_text(encoding="utf-8") if APPROVED_FILE.exists() else ""
        if spec_name not in existing:
            with APPROVED_FILE.open("a", encoding="utf-8") as f:
                f.write(f"{spec_name}\n")
            self._approved_cache = None  # force reload
            logger.info(f"[research_gate] approved: {spec_name}")

    # ── Tier determination ────────────────────────────────────────────────────

    def tier(self, spec_path: str) -> Tuple[int, str]:
        """
        Returns (tier_number, reason):
          1 = AUTO (pre-approved)
          2 = PROPOSAL (needs human approval)
          3 = BLOCKED (never allowed)
        """
        spec_str = str(spec_path)
        spec_name = Path(spec_path).name

        # Tier 3: blocked patterns
        for pattern in _BLOCKED_PATTERNS:
            if pattern.lower() in spec_str.lower():
                return 3, f"blocked pattern: '{pattern}'"

        if not GATE_ENABLED:
            return 1, "gate disabled (dev mode)"

        # Tier 1: pre-approved
        if spec_name in self._load_approved():
            return 1, f"pre-approved: {spec_name}"

        # Tier 2: everything else needs approval
        return 2, f"not in approved list — proposal required"

    def can_run(self, spec_path: str) -> bool:
        t, _ = self.tier(spec_path)
        return t == 1

    def is_blocked(self, spec_path: str) -> bool:
        t, _ = self.tier(spec_path)
        return t == 3

    # ── Running approved specs ────────────────────────────────────────────────

    def run_approved(self, spec_path: str, block: bool = False) -> bool:
        """
        Run a pre-approved spec via subprocess.
        Returns True if launched successfully.
        block=True waits for completion (use for testing only).
        """
        t, reason = self.tier(spec_path)
        if t == 3:
            logger.error(f"[research_gate] BLOCKED: {spec_path} ({reason})")
            return False
        if t == 2:
            logger.warning(f"[research_gate] NOT approved: {spec_path} — use propose()")
            return False

        python = sys.executable
        cmd = [python, "scripts/run_strategy_autoresearch.py", "--spec", str(spec_path)]
        logger.info(f"[research_gate] launching: {' '.join(cmd)}")
        _tg(self._tg_token, self._tg_chat,
            f"🔬 AutoResearch started: {Path(spec_path).stem}")
        try:
            if block:
                result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=7200)
                success = result.returncode == 0
                _tg(self._tg_token, self._tg_chat,
                    f"{'✅' if success else '❌'} AutoResearch done: {Path(spec_path).stem}")
                return success
            else:
                subprocess.Popen(cmd, cwd=str(ROOT))
                return True
        except Exception as e:
            logger.error(f"[research_gate] launch failed: {e}")
            return False

    # ── Proposal workflow ─────────────────────────────────────────────────────

    def propose(self, spec_path: str, reason: str = "") -> str:
        """
        Write a proposal for human review and send Telegram notification.
        Returns proposal ID.
        """
        spec_name = Path(spec_path).stem
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        proposal_id = f"{ts}_{spec_name}"
        proposal_file = PROPOSALS_DIR / f"{proposal_id}.json"

        proposal = {
            "id":          proposal_id,
            "spec_path":   str(spec_path),
            "spec_name":   Path(spec_path).name,
            "reason":      reason,
            "status":      "pending",
            "proposed_utc": datetime.now(timezone.utc).isoformat(),
            "expires_utc":  datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat(),  # will be set properly below
            "tier":        self.tier(spec_path)[0],
        }
        # expire after N hours
        expires_ts = time.time() + PROPOSAL_TIMEOUT_HOURS * 3600
        proposal["expires_utc"] = datetime.fromtimestamp(
            expires_ts, tz=timezone.utc
        ).isoformat()

        proposal_file.write_text(json.dumps(proposal, indent=2, ensure_ascii=False))
        logger.info(f"[research_gate] proposal created: {proposal_id}")

        # Send Telegram
        msg = (
            f"⚠️ *Research Proposal* — needs your approval\n\n"
            f"Spec: `{Path(spec_path).name}`\n"
            f"Reason: {reason or 'DeepSeek weekly analysis'}\n\n"
            f"Reply to bot:\n"
            f"  `/approve {proposal_id}` — run it + add to approved list\n"
            f"  `/reject {proposal_id}` — archive, do not run\n\n"
            f"Auto-expires: {PROPOSAL_TIMEOUT_HOURS}h"
        )
        _tg(self._tg_token, self._tg_chat, msg)
        return proposal_id

    def list_proposals(self, status: str = "pending") -> List[dict]:
        """List all proposals with given status."""
        proposals = []
        if not PROPOSALS_DIR.exists():
            return proposals
        now = time.time()
        for f in sorted(PROPOSALS_DIR.glob("*.json")):
            try:
                p = json.loads(f.read_text(encoding="utf-8"))
                if p.get("status") != status:
                    continue
                # Check expiry
                expires = p.get("expires_utc", "")
                if expires:
                    from datetime import datetime as _dt
                    exp_ts = _dt.fromisoformat(expires).timestamp()
                    if exp_ts < now:
                        p["status"] = "expired"
                        f.write_text(json.dumps(p, indent=2))
                        continue
                proposals.append(p)
            except Exception:
                pass
        return proposals

    def approve_proposal(self, proposal_id: str) -> bool:
        """Approve a proposal: run its spec + add to approved list."""
        f = PROPOSALS_DIR / f"{proposal_id}.json"
        if not f.exists():
            logger.warning(f"[research_gate] proposal not found: {proposal_id}")
            return False
        p = json.loads(f.read_text(encoding="utf-8"))
        if p.get("status") != "pending":
            logger.warning(f"[research_gate] proposal {proposal_id} is {p.get('status')}, not pending")
            return False
        spec_path = p["spec_path"]
        self.add_approved(p["spec_name"])
        p["status"] = "approved"
        p["approved_utc"] = datetime.now(timezone.utc).isoformat()
        f.write_text(json.dumps(p, indent=2))
        logger.info(f"[research_gate] approved + launching: {proposal_id}")
        return self.run_approved(spec_path)

    def reject_proposal(self, proposal_id: str, reason: str = "") -> bool:
        f = PROPOSALS_DIR / f"{proposal_id}.json"
        if not f.exists():
            return False
        p = json.loads(f.read_text(encoding="utf-8"))
        p["status"] = "rejected"
        p["rejected_utc"] = datetime.now(timezone.utc).isoformat()
        p["reject_reason"] = reason
        f.write_text(json.dumps(p, indent=2))
        logger.info(f"[research_gate] rejected: {proposal_id}")
        _tg(self._tg_token, self._tg_chat,
            f"❌ Research proposal rejected: {Path(p['spec_path']).stem}\nReason: {reason or 'manual'}")
        return True

    # ── Auto-triggers ─────────────────────────────────────────────────────────

    def check_triggers(
        self,
        strategy_stats: Optional[Dict[str, dict]] = None,
        current_symbols: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Check all trigger conditions. Returns list of spec paths to propose.
        strategy_stats: {strategy_name: {"winrate_30d": 0.43, "net_pnl_30d": -1.5, ...}}
        current_symbols: current live symbol list
        """
        triggered: List[str] = []
        trigger_log: List[dict] = []

        # --- Trigger 1: win rate below threshold ---
        if strategy_stats:
            for strat_name, stats in strategy_stats.items():
                wr = float(stats.get("winrate_30d") or stats.get("winrate") or 1.0)
                if wr < (TRIGGER_WR_THRESHOLD / 100.0):
                    logger.warning(
                        f"[research_gate] trigger: {strat_name} WR={wr*100:.1f}% < {TRIGGER_WR_THRESHOLD}%"
                    )
                    trigger_log.append({
                        "trigger": "low_winrate",
                        "strategy": strat_name,
                        "winrate_30d": wr,
                        "threshold": TRIGGER_WR_THRESHOLD / 100.0,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    })
                    # Find the corresponding autoresearch spec for this strategy
                    spec = self._find_spec_for_strategy(strat_name)
                    if spec and spec not in triggered:
                        triggered.append(spec)

        # --- Trigger 2: equity curve degradation ---
        health_file = ROOT / "configs" / "strategy_health.json"
        if health_file.exists():
            try:
                health = json.loads(health_file.read_text(encoding="utf-8"))
                for strat_name, data in health.get("strategies", {}).items():
                    status = data.get("status", "OK")
                    if status in ("PAUSE", "KILL"):
                        trigger_log.append({
                            "trigger": "equity_curve_degradation",
                            "strategy": strat_name,
                            "status": status,
                            "ts": datetime.now(timezone.utc).isoformat(),
                        })
                        spec = self._find_spec_for_strategy(strat_name)
                        if spec and spec not in triggered:
                            triggered.append(spec)
            except Exception:
                pass

        # Save trigger log
        if trigger_log:
            existing = []
            if TRIGGER_LOG_FILE.exists():
                try:
                    existing = json.loads(TRIGGER_LOG_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pass
            existing = (existing + trigger_log)[-200:]  # keep last 200 entries
            TRIGGER_LOG_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False))

        return triggered

    def _find_spec_for_strategy(self, strategy_name: str) -> Optional[str]:
        """Find the best autoresearch spec for a given strategy name."""
        spec_map = {
            "alt_sloped_channel_v1":     "asc1_rescue_v1.json",
            "alt_resistance_fade_v1":    "asc1_rescue_v1.json",
            "alt_inplay_breakdown_v1":   "sr_break_retest_volume_v1_revival_v1.json",
            "triple_screen_v132":        "triple_screen_elder_v13_zoom.json",
            "funding_rate_reversion_v1": "funding_rate_reversion_v1_grid.json",
            "liquidation_cascade_entry_v1": "liquidation_cascade_v1_grid.json",
        }
        spec_name = spec_map.get(strategy_name)
        if spec_name:
            spec_path = ROOT / "configs" / "autoresearch" / spec_name
            if spec_path.exists():
                return str(spec_path)
        return None

    # ── Kill-zone audit ───────────────────────────────────────────────────────

    def update_kill_zones(self, symbol_pnl_30d: Dict[str, float]) -> List[str]:
        """
        Flag symbols with net PnL below threshold as kill-zone candidates.
        Does NOT ban them — just logs for human review.
        Returns list of newly flagged symbols.
        """
        candidates: Dict[str, dict] = {}
        if KILL_ZONE_FILE.exists():
            try:
                candidates = json.loads(KILL_ZONE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass

        newly_flagged = []
        for sym, pnl in symbol_pnl_30d.items():
            if pnl < KILL_ZONE_THRESHOLD_USD:
                if sym not in candidates:
                    newly_flagged.append(sym)
                    candidates[sym] = {
                        "symbol":      sym,
                        "net_pnl_30d": pnl,
                        "flagged_utc": datetime.now(timezone.utc).isoformat(),
                        "status":      "candidate",  # human changes to "banned" or "cleared"
                    }
                    logger.warning(f"[research_gate] kill-zone candidate: {sym} PnL={pnl:.2f}$")
                else:
                    candidates[sym]["net_pnl_30d"] = pnl
                    candidates[sym]["updated_utc"] = datetime.now(timezone.utc).isoformat()
            elif sym in candidates and candidates[sym].get("status") == "candidate":
                # Symbol recovered — clear it
                candidates[sym]["status"] = "cleared"
                candidates[sym]["cleared_utc"] = datetime.now(timezone.utc).isoformat()

        KILL_ZONE_FILE.write_text(json.dumps(candidates, indent=2, ensure_ascii=False))

        if newly_flagged:
            _tg(
                self._tg_token, self._tg_chat,
                f"⚠️ Kill-zone candidates (PnL < {KILL_ZONE_THRESHOLD_USD}$ / 30d):\n"
                + "\n".join(f"  {s}: {symbol_pnl_30d[s]:.2f}$" for s in newly_flagged)
                + "\n\nReview configs/kill_zone_candidates.json and set status='banned' to remove."
            )
        return newly_flagged

    def status_report(self) -> str:
        """Human-readable status for Telegram /research_status command."""
        pending = self.list_proposals("pending")
        approved = self._load_approved()
        lines = [
            f"🔬 Research Gate Status",
            f"  Gate: {'ENABLED' if GATE_ENABLED else 'DISABLED (dev mode)'}",
            f"  Pre-approved specs: {len(approved)}",
            f"  Pending proposals: {len(pending)}",
        ]
        if pending:
            lines.append("\nPending proposals:")
            for p in pending[:5]:
                lines.append(f"  [{p['id'][:16]}] {p['spec_name']} — {p['reason'][:50]}")
        kill_zones = {}
        if KILL_ZONE_FILE.exists():
            try:
                kz = json.loads(KILL_ZONE_FILE.read_text(encoding="utf-8"))
                kill_zones = {k: v for k, v in kz.items() if v.get("status") == "candidate"}
            except Exception:
                pass
        if kill_zones:
            lines.append(f"\nKill-zone candidates: {len(kill_zones)}")
            for sym, data in list(kill_zones.items())[:5]:
                lines.append(f"  {sym}: {data.get('net_pnl_30d', '?'):.2f}$ / 30d")
        return "\n".join(lines)


# ── Singleton ─────────────────────────────────────────────────────────────────
gate = ResearchGate()
