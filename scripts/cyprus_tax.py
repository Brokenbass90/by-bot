#!/usr/bin/env python3
"""Cyprus crypto tax set-aside estimator (Opus 2026-06-08).

⚠ NOT TAX ADVICE. A planning helper that suggests how much to set aside, with an
explicit disclaimer. Cyprus crypto taxation depends on facts the bot cannot know:
  - tax residency (e.g. 60-day / 183-day rules) and non-dom status;
  - whether activity is classified as INVESTING (capital gains) or TRADING
    (frequent, business-like) — the classification drives the rate;
  - current law, which changes.

General (NON-binding) picture used as defaults — confirm with a Cyprus tax advisor:
  - Individual capital gains on crypto: commonly 0% (Cyprus taxes capital gains
    only on immovable property) → 'investment' default rate 0%.
  - If reclassified as a trade/business: taxed as income — conservative default 12.5%.
Rates are CONFIGURABLE; the tool never hard-asserts a legal outcome.
"""
from __future__ import annotations

import argparse
from typing import Any, Dict

DISCLAIMER = (
    "НЕ юридическая/налоговая консультация. Оценка зависит от резидентства, non-dom "
    "статуса и классификации (инвестиции vs трейдинг). Свериться с кипрским "
    "налоговым консультантом перед любыми решениями."
)


def estimate_set_aside(
    realized_profit: float,
    classification: str = "trading",
    investment_rate: float = 0.0,
    trading_rate: float = 0.125,
) -> Dict[str, Any]:
    """Suggest a tax set-aside for realized PROFIT (losses → 0).

    classification: 'investment' (capital gains, default 0% in Cyprus) or
    'trading' (business income, conservative default 12.5%).
    """
    profit = max(0.0, float(realized_profit))
    cls = str(classification or "trading").lower()
    rate = investment_rate if cls == "investment" else trading_rate
    rate = max(0.0, min(1.0, float(rate)))
    set_aside = round(profit * rate, 2)
    return {
        "realized_profit": round(float(realized_profit), 2),
        "taxable_base": round(profit, 2),
        "classification": cls,
        "applied_rate_pct": round(rate * 100.0, 2),
        "suggested_set_aside": set_aside,
        "keep_after_set_aside": round(profit - set_aside, 2),
        "disclaimer": DISCLAIMER,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profit", type=float, required=True)
    ap.add_argument("--classification", default="trading", choices=["investment", "trading"])
    ap.add_argument("--trading-rate", type=float, default=0.125)
    ap.add_argument("--investment-rate", type=float, default=0.0)
    args = ap.parse_args()
    r = estimate_set_aside(args.profit, args.classification, args.investment_rate, args.trading_rate)
    print(f"Profit {r['realized_profit']} | {r['classification']} @ {r['applied_rate_pct']}% "
          f"→ set aside {r['suggested_set_aside']}, keep {r['keep_after_set_aside']}")
    print("⚠ " + r["disclaimer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
