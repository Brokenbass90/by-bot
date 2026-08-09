"""Pure policy guards for the legacy position-management path.

The monolith still contains the original pump-fade DCA manager.  Keeping its
strategy scope in a pure helper makes it difficult for unrelated strategies to
inherit averaging behaviour accidentally.
"""

from __future__ import annotations


_LEGACY_PUMP_FADE_DCA_STRATEGIES = frozenset({"pump", "pump_fade"})


def should_apply_legacy_pump_fade_dca(strategy: object) -> bool:
    """Return true only for the two names owned by the legacy DCA manager."""

    return str(strategy or "").strip().lower() in _LEGACY_PUMP_FADE_DCA_STRATEGIES
