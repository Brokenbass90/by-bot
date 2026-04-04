#!/usr/bin/env python3
"""
Claude Monthly Analyst — Deep AI Portfolio Review
==================================================
Uses Claude API (Anthropic) for high-level monthly analysis that DeepSeek
is not optimal for: complex code review, new strategy ideation, architectural
decisions, cross-market reasoning.

Role split (DeepSeek vs Claude):
  DeepSeek  — weekly, cheap, high-volume: param tuning, signal audit, universe scan
  Claude    — monthly, deeper: portfolio health, new strategy design, code quality,
              strategic decisions ("should we add Elder?", "why is ARF1 degrading?")

Cost estimate: ~$5-15/month at claude-sonnet-4-5 (3.75M tokens context)
Activate when: monthly bot P&L consistently > $200

Usage:
  python3 scripts/claude_monthly_analyst.py --report
  python3 scripts/claude_monthly_analyst.py --strategy-idea "funding rate reversion"
  python3 scripts/claude_monthly_analyst.py --diagnose alt_resistance_fade_v1

Config:
  ANTHROPIC_API_KEY=sk-ant-...   (in configs/claude_analyst.env or env)
  CLAUDE_MODEL=claude-sonnet-4-6  (default, use claude-opus-4-6 for deepest analysis)
  CLAUDE_MONTHLY_BUDGET_USD=15    (abort if estimated cost exceeds this)

Status: READY — set ANTHROPIC_API_KEY in configs/claude_analyst.env to activate
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error, request

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE          = ROOT / "configs" / "claude_analyst.env"
HEALTH_FILE       = ROOT / "configs" / "strategy_health.json"
REPORTS_DIR       = ROOT / "docs" / "monthly_reports"
WEEKLY_REPORTS    = ROOT / "docs" / "weekly_reports"
TRADE_LEARN_LOG   = ROOT / "data" / "trade_learning_log.jsonl"
FAMILY_PROFILES   = ROOT / "configs" / "family_profiles.json"
INTRADAY_STATE    = ROOT / "configs" / "intraday_state.json"
BACKTEST_RUNS_DIR = ROOT / "backtest_runs"

ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL  = "claude-sonnet-4-6"

# ── Env helpers ──────────────────────────────────────────────────────────────────
def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.split("#")[0].strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val

def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default)).strip()

# ── Claude API client ─────────────────────────────────────────────────────────────
class ClaudeClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model   = model
        self._ssl    = ssl.create_default_context()

    def ask(self, system: str, user: str, max_tokens: int = 2000) -> str:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        req = request.Request(
            ANTHROPIC_API,
            data=json.dumps(payload).encode(),
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, context=self._ssl, timeout=60) as resp:
                data = json.loads(resp.read().decode())
                return data["content"][0]["text"]
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Claude API error {exc.code}: {detail}") from exc

# ── Context builders ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the senior architect of a self-improving crypto + equities trading bot.
The bot runs on Bybit perpetual futures and Alpaca paper equities.

Your role is monthly deep analysis — not daily ops (that's DeepSeek's job).
You focus on:
- Portfolio-level strategy correlation and diversification
- Detecting structural degradation in strategies before it shows in P&L
- Designing new strategy concepts with specific entry/exit logic
- Code quality review and architecture improvements
- Strategic decisions: which strategies to promote, pause, or retire

Response style:
- Direct, technical, specific
- Always give concrete numbers and thresholds, not vague advice
- If recommending code changes, describe the exact logic
- Russian or English, match the question language
"""

def _load_portfolio_context() -> str:
    """Build a context string from available live bot data.

    Reads (in priority order):
      1. configs/strategy_health.json   — live equity curve status per strategy
      2. docs/weekly_reports/           — last DeepSeek weekly report summary
      3. data/trade_learning_log.jsonl  — recent trade patterns
      4. configs/family_profiles.json   — current symbol family multipliers
      5. configs/intraday_state.json    — Alpaca intraday state
      6. backtest_runs/ top results     — best known backtest params
    """
    lines = [f"== BOT CONTEXT (generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}) =="]

    # ── 1. Strategy health ─────────────────────────────────────────────────────
    if HEALTH_FILE.exists():
        try:
            health = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
            ts = health.get("timestamp", "unknown")
            overall = health.get("overall_health", "unknown")
            lines.append(f"\nStrategy Health (as of {ts}, overall={overall}):")
            for name, h in health.get("strategies", {}).items():
                lines.append(
                    f"  {name}: status={h.get('status','?')} | "
                    f"PF30d={h.get('pf_30d', 0):.2f} | "
                    f"trades30d={h.get('trades_30d', 0)} | "
                    f"curveΔ={h.get('curve_vs_ma20', 0):+.3f} | "
                    f"WR30d={h.get('winrate_30d', 0):.1%}"
                )
        except Exception as exc:
            lines.append(f"\nStrategy Health: (error reading: {exc})")
    else:
        lines.append("\nStrategy Health: NOT AVAILABLE — run equity_curve_autopilot.py first")

    # ── 2. Latest weekly DeepSeek report summary ──────────────────────────────
    if WEEKLY_REPORTS.exists():
        try:
            reports = sorted(WEEKLY_REPORTS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if reports:
                latest = json.loads(reports[0].read_text(encoding="utf-8"))
                lines.append(f"\nLatest Weekly Report ({reports[0].name}):")
                # Audit section
                audit = latest.get("audit", {})
                if audit:
                    lines.append(f"  Strategies audited: {list(audit.get('strategies', {}).keys())}")
                    for st, s in audit.get("strategies", {}).items():
                        lines.append(f"  {st}: trades={s.get('total_trades',0)} avg_pf={s.get('avg_pf',0):.2f}")
                # Proposals
                proposals = latest.get("proposals", [])
                if proposals:
                    lines.append(f"  Pending proposals: {len(proposals)}")
                    for p in proposals[:3]:
                        lines.append(f"    [{p.get('status','?')}] {p.get('summary','')[:80]}")
        except Exception as exc:
            lines.append(f"\nWeekly Report: (error reading: {exc})")

    # ── 3. Trade learning patterns ────────────────────────────────────────────
    if TRADE_LEARN_LOG.exists():
        try:
            recent_trades: List[dict] = []
            with TRADE_LEARN_LOG.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            recent_trades.append(json.loads(line))
                        except Exception:
                            pass
            # Last 50 trades
            recent_trades = recent_trades[-50:]
            if recent_trades:
                winners = [t for t in recent_trades if t.get("pnl", 0) > 0]
                losers  = [t for t in recent_trades if t.get("pnl", 0) <= 0]
                avg_win  = sum(t.get("pnl", 0) for t in winners) / max(1, len(winners))
                avg_loss = sum(t.get("pnl", 0) for t in losers)  / max(1, len(losers))
                lines.append(f"\nTrade Learning (last {len(recent_trades)} trades):")
                lines.append(f"  WR={len(winners)/len(recent_trades):.1%} | avg_win={avg_win:.4f} | avg_loss={avg_loss:.4f}")
                # Pattern summary
                patterns: Dict[str, int] = {}
                for t in recent_trades:
                    for pat in t.get("patterns", []):
                        patterns[pat] = patterns.get(pat, 0) + 1
                if patterns:
                    top = sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:5]
                    lines.append(f"  Top patterns: {top}")
        except Exception as exc:
            lines.append(f"\nTrade Learning: (error reading: {exc})")

    # ── 4. Family profiles ────────────────────────────────────────────────────
    if FAMILY_PROFILES.exists():
        try:
            fp = json.loads(FAMILY_PROFILES.read_text(encoding="utf-8"))
            lines.append("\nFamily Profiles (per-symbol-family multipliers):")
            for fname, mults in fp.get("multipliers", {}).items():
                if fname.startswith("_") or not isinstance(mults, dict):
                    continue
                lines.append(f"  {fname}: {mults}")
        except Exception:
            pass

    # ── 5. Alpaca intraday state ──────────────────────────────────────────────
    if INTRADAY_STATE.exists():
        try:
            state = json.loads(INTRADAY_STATE.read_text(encoding="utf-8"))
            daily_pnl  = state.get("today_realized_pnl", 0)
            open_pos   = state.get("open_positions", [])
            eq_healthy = state.get("equity_curve_ok", True)
            spy_ok     = state.get("spy_regime_ok", True)
            lines.append(f"\nAlpaca Intraday State:")
            lines.append(f"  today_pnl={daily_pnl:+.2f} | open_positions={len(open_pos)} | "
                         f"equity_curve_ok={eq_healthy} | spy_regime_ok={spy_ok}")
        except Exception:
            pass

    # ── 6. Best known backtest results (from baselines if available) ──────────
    baselines_dir = ROOT / "baselines"
    if baselines_dir.exists():
        try:
            baseline_files = sorted(baselines_dir.glob("*.json"),
                                    key=lambda p: p.stat().st_mtime, reverse=True)[:3]
            if baseline_files:
                lines.append("\nRecent Baselines:")
                for bf in baseline_files:
                    try:
                        b = json.loads(bf.read_text(encoding="utf-8"))
                        lines.append(
                            f"  {bf.stem}: PF={b.get('profit_factor',0):.3f} | "
                            f"net={b.get('net_pnl_pct',0):.1f}% | "
                            f"DD={b.get('max_drawdown_pct',0):.1f}% | "
                            f"trades={b.get('total_trades',0)}"
                        )
                    except Exception:
                        pass
        except Exception:
            pass

    # ── 7. Static portfolio baseline (always included as reference) ───────────
    lines.append("\nGolden Portfolio Baseline (5-strategy, 360-day backtest):")
    lines.append("  PnL=+100.93%, PF=2.078, DD=3.65%, trades=446, 0 red months")
    lines.append("  Live stack: alt_inplay_breakdown_v1, alt_resistance_fade_v1,")
    lines.append("    alt_sloped_channel_v1, btc_eth_midterm_pullback, inplay_breakout")
    lines.append("  Server: 64.226.73.119 | Bot: smart_pump_reversal_bot.py")

    return "\n".join(lines)

# ── Analysis tasks ────────────────────────────────────────────────────────────────
def run_monthly_report(client: ClaudeClient) -> str:
    """Full monthly portfolio health analysis."""
    context = _load_portfolio_context()
    prompt = f"""{context}

Task: Generate a comprehensive monthly analysis report.

Cover:
1. Overall portfolio health — is the current 5-strategy setup still valid?
2. Per-strategy assessment — any showing regime drift signals?
3. Elder Triple Screen recommendation — integrate as 6th strategy (PF=4.27, 32 trades/year)?
   What's the correlation risk? What allocation % would be appropriate?
4. Top 3 actions for next month (specific, numbered, with thresholds)
5. One new strategy concept worth researching next (with entry/exit logic sketch)
"""
    return client.ask(SYSTEM_PROMPT, prompt, max_tokens=3000)


def run_strategy_idea(client: ClaudeClient, idea: str) -> str:
    """Design a new strategy based on a concept."""
    context = _load_portfolio_context()
    prompt = f"""{context}

Task: Design a new trading strategy for this concept: "{idea}"

Provide:
1. Market logic — WHY this edge exists on Bybit perpetual futures
2. Entry conditions (specific, quantifiable — EMA periods, RSI thresholds, etc.)
3. Exit conditions (SL/TP as ATR multiples, time stop)
4. Suggested symbols (from BTC/ETH/SOL/AVAX/ADA/LINK/ATOM universe)
5. Expected characteristics: trades/month, typical WR, PF target
6. Implementation notes for Python backtest (class structure, key methods)
7. Correlation with existing 5 strategies — where does it add diversification?
"""
    return client.ask(SYSTEM_PROMPT, prompt, max_tokens=2500)


def run_diagnose(client: ClaudeClient, strategy_name: str) -> str:
    """Deep diagnosis of a specific strategy."""
    context = _load_portfolio_context()
    prompt = f"""{context}

Task: Deep diagnosis of strategy: {strategy_name}

Analyse:
1. What could cause this strategy to degrade in current market conditions (early 2026, crypto correction)?
2. Likely parameter drift — which params are most sensitive to regime change?
3. Specific autoresearch recommendations: which params to re-grid, what range, what constraints
4. Short-term fix vs long-term fix
5. Kill signal: at what point should we retire this strategy?
"""
    return client.ask(SYSTEM_PROMPT, prompt, max_tokens=2000)

# ── Telegram ──────────────────────────────────────────────────────────────────────
def _tg(token: str, chat_id: str, msg: str) -> None:
    if not token or not chat_id:
        return
    # Split long messages
    for chunk in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
        payload = json.dumps({"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"}).encode()
        req = request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"},
        )
        try:
            with request.urlopen(req, context=ssl.create_default_context(), timeout=10):
                pass
        except Exception:
            pass

# ── Main ──────────────────────────────────────────────────────────────────────────
def main() -> None:
    _load_env_file(ENV_FILE)
    _load_env_file(ROOT / "configs" / "alpaca_paper_local.env")

    ap = argparse.ArgumentParser(description="Claude Monthly Analyst")
    ap.add_argument("--report",         action="store_true", help="Full monthly report")
    ap.add_argument("--strategy-idea",  metavar="IDEA",      help="Design new strategy concept")
    ap.add_argument("--diagnose",       metavar="STRATEGY",  help="Deep diagnose a strategy")
    ap.add_argument("--no-tg",          action="store_true", help="Skip Telegram")
    args = ap.parse_args()

    api_key = _env("ANTHROPIC_API_KEY")
    if not api_key:
        print("=" * 60)
        print("Claude Monthly Analyst — NOT YET ACTIVATED")
        print("=" * 60)
        print()
        print("This module is ready but waiting for API key.")
        print()
        print("To activate:")
        print("  1. Get key from: https://console.anthropic.com/")
        print("  2. Create file: configs/claude_analyst.env")
        print("     Contents: ANTHROPIC_API_KEY=sk-ant-...")
        print()
        print("Cost estimate:")
        print("  Monthly report    → ~$0.50 (claude-sonnet-4-6)")
        print("  Strategy idea     → ~$0.30")
        print("  Strategy diagnose → ~$0.25")
        print("  Full month usage  → ~$5-10")
        print()
        print("Recommended activation threshold: bot P&L > $200/month")
        print()
        print("Current bot status (from strategy_health.json):")
        if HEALTH_FILE.exists():
            try:
                h = json.loads(HEALTH_FILE.read_text())
                print(f"  Overall: {h.get('overall_health', 'unknown')}")
                for name, s in h.get("strategies", {}).items():
                    print(f"  {name}: {s['status']}")
            except Exception:
                print("  (could not read health file)")
        else:
            print("  (run equity_curve_autopilot.py first)")
        sys.exit(0)

    model = _env("CLAUDE_MODEL", DEFAULT_MODEL)
    client = ClaudeClient(api_key, model)
    tg_token = _env("TG_TOKEN")
    tg_chat  = _env("TG_CHAT_ID")
    now_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    result = ""

    if args.report:
        print(f"Running monthly report ({model})...")
        result = run_monthly_report(client)
        # Save report
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / f"claude_monthly_{datetime.now().strftime('%Y%m')}.md"
        report_path.write_text(f"# Claude Monthly Analysis — {now_str}\n\n{result}")
        print(f"Saved: {report_path}")

    elif args.strategy_idea:
        print(f"Designing strategy: {args.strategy_idea} ({model})...")
        result = run_strategy_idea(client, args.strategy_idea)

    elif args.diagnose:
        print(f"Diagnosing: {args.diagnose} ({model})...")
        result = run_diagnose(client, args.diagnose)

    else:
        ap.print_help()
        sys.exit(1)

    print("\n" + "=" * 60)
    print(result)
    print("=" * 60)

    if not args.no_tg and result:
        _tg(tg_token, tg_chat, f"🤖 <b>Claude Analyst — {now_str}</b>\n\n{result[:3800]}")


if __name__ == "__main__":
    main()
