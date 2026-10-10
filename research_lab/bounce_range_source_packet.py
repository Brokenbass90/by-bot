"""Pure closed H1 -> UTC H4 derivation; no signals, outcomes, fetch or orders.

The legacy NPZ builder labels H1 bars by OPEN time. Count=12 is only its
declared M5 count: this module cannot certify the missing raw M5 lineage or
historical publication/availability times.
"""
from numbers import Integral

from bot.closed_bar_aggregation_v1 import canonical_bars_bytes

HOUR_MS = 3_600_000
H4_MS = 4 * HOUR_MS


def derive_closed_h4(rows, nsub, *, as_of_ms):
    """Require a contiguous closed H1 prefix; explicitly exclude partial edges.

    A caller must select its closed prefix before calling. No sorting, dedup,
    filling, shifted buckets, partial-hour acceptance or open-tail removal is
    hidden here. Prices retain the precision of the provided H1 source.
    """
    if (isinstance(as_of_ms, bool) or not isinstance(as_of_ms, Integral)
            or as_of_ms < 0):
        raise ValueError('INVALID_AS_OF')
    if not len(rows) or len(rows) != len(nsub):
        raise ValueError('H1_ROWS_OR_COUNTS_MISSING')
    previous = None
    normal = []
    for row, count in zip(rows, nsub):
        if len(row) != 6:
            raise ValueError('H1_ROW_SHAPE')
        ts = row[0]
        if (isinstance(ts, bool) or not isinstance(ts, Integral) or ts < 0
                or ts % HOUR_MS or (previous is not None and ts != previous + HOUR_MS)):
            raise ValueError('H1_GRID_OR_TIMESTAMP')
        if ts + HOUR_MS > as_of_ms:
            raise ValueError('OPEN_OR_FUTURE_H1')
        if isinstance(count, bool) or not isinstance(count, Integral) or count != 12:
            raise ValueError('H1_SUBBAR_COUNT')
        normal.append([int(ts), *row[1:]])
        previous = int(ts)
    # Reuse the project's strict finite-price/OHLC/volume validation.
    canonical_bars_bytes(normal)
    first = ((normal[0][0] + H4_MS - 1) // H4_MS) * H4_MS
    end = ((normal[-1][0] + HOUR_MS) // H4_MS) * H4_MS
    core = [r for r in normal if first <= r[0] < end]
    if not core:
        raise ValueError('NO_COMPLETE_H4_BUCKET')
    result = []
    for offset in range(0, len(core), 4):
        children = core[offset:offset + 4]
        if len(children) != 4 or children[0][0] % H4_MS:
            raise ValueError('INCOMPLETE_H4_BUCKET')
        result.append([children[0][0], float(children[0][1]),
                       max(float(r[2]) for r in children),
                       min(float(r[3]) for r in children), float(children[-1][4]),
                       sum(float(r[5]) for r in children)])
    canonical_bars_bytes(result)
    return {'rows': result, 'excluded_leading_open_ms': [r[0] for r in normal if r[0] < first],
            'excluded_trailing_open_ms': [r[0] for r in normal if r[0] >= end],
            'last_available_ms': result[-1][0] + H4_MS}
