"""Research-only cross-exchange funding station, model v3.

The package intentionally contains no authenticated exchange client and no order
submission path.  The supervisor consumes a local bundle of already-collected
public responses so its lineage and accounting can be tested without credentials,
capital, or live side effects.
"""

from .supervisor import (
    MODEL_VERSION,
    STAGE_ORDER,
    AlreadyRunning,
    SettlementExecutionV3Supervisor,
    StageFailure,
)

__all__ = [
    "MODEL_VERSION",
    "STAGE_ORDER",
    "AlreadyRunning",
    "SettlementExecutionV3Supervisor",
    "StageFailure",
]
