"""Frozen Brain V2 primitives, without an autonomous allocator or order path.

Only assessment of supplied evidence/proposed portfolios is implemented here.
Train statistics and VOL percentile are external immutable inputs; this module
does not fit them, select a subset, ingest outcomes or mutate any portfolio.
The missing frozen estimator/subset contracts block integrated readiness.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re

from bot import regime_orchestrator

HOUR = 3_600_000
DEVELOP_END_EXCLUSIVE_MS = 1_759_276_800_000  # 2025-10-01 UTC, spec section 6.
REGIMES = ('BULL', 'BEAR', 'NEUTRAL')
VOLS = ('LOW', 'MID', 'HIGH')
ARMS = ('RAW_SAFE', 'FOUNDATION', 'BRAIN_DET')
REGIME_PIN = '56952650bd2dcb09421e87a2f5d4f9a27d1184b7ce64504f7f8ed54e00f85370'
PARAMS_PIN = '305a00c7a752bec7cf97c647d5660e21ccc7a7e115cef21c3d436ab4c0dbc157'
SPEC_PIN = 'f96b73eca3607af7f997b821c2fe76fa8c868b8abc09d2ada64d0f2a54bfd6c0'


class BrainBlocked(ValueError):
    status = 'BLOCKED_DATA'


def _require(ok, reason):
    if not ok:
        raise BrainBlocked(reason)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _pin(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _identity(value):
    # Symbols may contain venue-native Unicode. Identity validation must not
    # introduce an ASCII-only universe filter or silently transliterate names.
    return isinstance(value, str) and bool(re.fullmatch(r'[\w.:/-]{1,128}', value))


def _time(value):
    return type(value) is int and value >= 0


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class Opportunity:
    sleeve: str
    symbol: str
    side: str
    t_signal: int
    t_available: int
    entry_rule: str
    stop_distance_frac: float
    max_hold_h: float
    cost_model_id: str
    source_hash: str

    def __post_init__(self):
        _require(all(_identity(x) for x in (self.sleeve, self.symbol, self.entry_rule, self.cost_model_id)),
                 'opportunity_identity')
        _require(self.side in ('long', 'short'), 'opportunity_side')
        _require(_time(self.t_signal) and _time(self.t_available) and self.t_signal <= self.t_available,
                 'opportunity_availability')
        _require(_number(self.stop_distance_frac) and self.stop_distance_frac > 0,
                 'opportunity_stop_distance')
        _require(_number(self.max_hold_h) and self.max_hold_h > 0, 'opportunity_hold')
        _require(_pin(self.source_hash), 'opportunity_source_pin')

    @property
    def id(self):
        return digest(asdict(self))

    @property
    def batch_hour(self):
        return self.t_available // HOUR


@dataclass(frozen=True)
class CellStats:
    regime: str
    vol: str
    n: int
    mean_r: float


@dataclass(frozen=True)
class FrozenStats:
    sleeve: str
    n: int
    mean_r: float
    sigma_r: float
    cells: tuple[CellStats, ...]
    frozen_at_ms: int
    last_outcome_available_ms: int
    source_hash: str


@dataclass(frozen=True)
class Score:
    mu_s: float
    mu_context: float
    z: float
    multiplier: float
    context_status: str
    stats_source_hash: str


def score(opportunity: Opportunity, stats: FrozenStats, regime: str, vol: str) -> Score:
    _require(stats.sleeve == opportunity.sleeve, 'statistics_sleeve')
    _require(type(stats.n) is int and stats.n >= 0 and _number(stats.mean_r), 'statistics_counts')
    _require(stats.n > 0 or stats.mean_r == 0, 'statistics_empty_mean')
    _require(_number(stats.sigma_r) and stats.sigma_r > 0, 'statistics_sigma_unknown_or_zero')
    _require(_time(stats.frozen_at_ms) and _time(stats.last_outcome_available_ms)
             and stats.last_outcome_available_ms <= stats.frozen_at_ms <= opportunity.t_available,
             'statistics_not_frozen_before_available')
    _require(stats.last_outcome_available_ms < DEVELOP_END_EXCLUSIVE_MS,
             'statistics_post_develop_outcome')
    _require(_pin(stats.source_hash), 'statistics_source_pin')
    _require(type(stats.cells) is tuple, 'statistics_immutable_cells')
    cells = {}
    for cell in stats.cells:
        key = (cell.regime, cell.vol)
        _require(cell.regime in REGIMES and cell.vol in VOLS and key not in cells,
                 'statistics_cell_identity')
        _require(type(cell.n) is int and cell.n >= 0 and _number(cell.mean_r), 'statistics_cell_counts')
        _require(cell.n > 0 or cell.mean_r == 0, 'statistics_cell_empty_mean')
        cells[key] = cell
    _require(sum(cell.n for cell in stats.cells) <= stats.n, 'statistics_population_conflict')
    _require(regime in (*REGIMES, 'UNKNOWN') and vol in (*VOLS, 'UNKNOWN'), 'context_labels')
    mu_s = stats.n * stats.mean_r / (stats.n + 300)
    if regime == 'UNKNOWN' or vol == 'UNKNOWN':
        mu_context, status = mu_s, 'UNKNOWN_SLEEVE_FALLBACK'
    else:
        _require((regime, vol) in cells, 'statistics_cell_missing_not_zero')
        cell = cells[(regime, vol)]
        mu_context = (cell.n * cell.mean_r + 150 * mu_s) / (cell.n + 150)
        status = 'KNOWN_CONTEXT'
    z = mu_context / stats.sigma_r
    _require(all(math.isfinite(x) for x in (mu_s, mu_context, z)), 'statistics_numeric_overflow')
    return Score(mu_s, mu_context, z, min(1.5, max(.5, 1 + 4*z)), status, stats.source_hash)


def rank(opportunities, tables, regime, vol, arm):
    """Ordering only: no positive-expectancy veto or portfolio mutation."""
    _require(arm in ARMS, 'arm_identity')
    xs = list(opportunities)
    _require(len({x.id for x in xs}) == len(xs), 'duplicate_opportunity')
    if arm in ('RAW_SAFE', 'FOUNDATION'):
        return sorted(xs, key=lambda x: (x.t_available, x.id))
    _require(all(x.sleeve in tables for x in xs), 'statistics_table_missing')
    return sorted(xs, key=lambda x: (-score(x, tables[x.sleeve], regime, vol).z, x.t_available, x.id))


@dataclass(frozen=True)
class RegimeBar:
    open_ms: int
    o: float
    h: float
    l: float
    c: float
    v: float
    available_ms: int


def regime_context(bars, as_of_ms, source_hash):
    """A1 last 200 BTC closed H4; last 60 must be contiguous. No file writer."""
    base = {'regime': 'UNKNOWN', 'reason': None, 'source_hash': source_hash,
            'as_of_ms': as_of_ms, 'orders_allowed': False}
    if not _time(as_of_ms) or not _pin(source_hash):
        return {**base, 'reason': 'regime_source_or_time_unknown'}
    if hashlib.sha256(Path(regime_orchestrator.__file__).read_bytes()).hexdigest() != REGIME_PIN:
        return {**base, 'reason': 'regime_code_pin_mismatch'}
    if not isinstance(bars, (list, tuple)) or not all(isinstance(b, RegimeBar) for b in bars):
        return {**base, 'reason': 'regime_bars_unknown'}
    xs = list(bars)
    if len(xs) < 60:
        return {**base, 'reason': 'regime_less_than_60'}
    # Caller supplies the complete sorted causal history, not future candles.
    for i, bar in enumerate(xs):
        values = (bar.o, bar.h, bar.l, bar.c, bar.v)
        if (not _time(bar.open_ms) or bar.open_ms % (4*HOUR)
                or not _time(bar.available_ms)
                or not bar.open_ms+4*HOUR <= bar.available_ms <= as_of_ms
                or not all(_number(x) for x in values)
                or min(bar.o, bar.h, bar.l, bar.c) <= 0 or bar.v < 0
                or not bar.l <= min(bar.o, bar.c) <= max(bar.o, bar.c) <= bar.h
                or (i and xs[i-1].open_ms >= bar.open_ms)):
            return {**base, 'reason': 'regime_invalid_or_unavailable_bar'}
    expected = as_of_ms // (4*HOUR) * (4*HOUR) - 4*HOUR
    if xs[-1].open_ms != expected:
        return {**base, 'reason': 'regime_expected_last_bar_missing'}
    if any(b.open_ms-a.open_ms != 4*HOUR for a,b in zip(xs[-60:], xs[-59:])):
        return {**base, 'reason': 'regime_last_60_not_contiguous'}
    result = regime_orchestrator.compute_regime(
        [[b.open_ms,b.o,b.h,b.l,b.c,b.v] for b in xs[-200:]])['regime']
    return {**base, 'regime': {'BULL_TREND':'BULL','BEAR_TREND':'BEAR','NEUTRAL':'NEUTRAL'}[result],
            'reason': 'A1_CLOSED_DATA', 'closed_cutoff_ms': expected+4*HOUR}


def vol_category(percentile, *, observed_ms, as_of_ms, method_pin):
    """Classify a supplied frozen percentile; no undeclared ATR/percentile math."""
    base = {'vol': 'UNKNOWN', 'method_pin': method_pin, 'observed_ms': observed_ms,
            'as_of_ms': as_of_ms, 'orders_allowed': False}
    if (not _number(percentile) or not 0 <= percentile <= 100 or not _pin(method_pin)
            or not _time(observed_ms) or not _time(as_of_ms) or observed_ms > as_of_ms):
        return {**base, 'reason': 'vol_frozen_estimator_or_source_unknown'}
    return {**base, 'vol': 'LOW' if percentile < 33 else 'HIGH' if percentile > 67 else 'MID',
            'reason': 'SUPPLIED_FROZEN_PERCENTILE', 'percentile': percentile}


@dataclass(frozen=True)
class PortfolioLeg:
    symbol: str
    sleeve: str
    side: str
    risk_usd: float
    source_hash: str


def assess_portfolio(legs, equity_usd, arm, *, protection_known):
    """Exact caps on an explicit COMPLETE proposal; this is not subset selection.

    Missing ledger/capital/protection blocks; no bootstrap/cap denominator change.
    The pure computation does not certify completeness or authenticated cash.
    """
    _require(arm in ARMS, 'arm_identity')
    base = {'arm': arm, 'orders_allowed': False, 'portfolio_mutated': False}
    if (not isinstance(legs, (list, tuple)) or not _number(equity_usd)
            or equity_usd <= 0 or protection_known is not True):
        return {**base, 'status': 'BLOCKED_DATA', 'reason': 'capital_positions_or_protection_unknown'}
    xs = list(legs)
    if any(not isinstance(x, PortfolioLeg) or not _identity(x.symbol)
           or not _identity(x.sleeve) or x.side not in ('long','short')
           or not _number(x.risk_usd) or x.risk_usd <= 0 or not _pin(x.source_hash) for x in xs):
        return {**base, 'status': 'BLOCKED_DATA', 'reason': 'portfolio_leg_unknown'}
    total = sum((Decimal(str(x.risk_usd)) for x in xs), Decimal(0))
    by_sleeve = {}
    net = Decimal(0)
    for x in xs:
        risk = Decimal(str(x.risk_usd))
        by_sleeve[x.sleeve] = by_sleeve.get(x.sleeve, Decimal(0)) + risk
        net += risk if x.side == 'long' else -risk
    errors = []
    if total > Decimal('.06') * Decimal(str(equity_usd)): errors.append('total_open_risk_cap')
    if len(xs) > 12: errors.append('position_cap')
    if len({x.symbol for x in xs}) != len(xs): errors.append('symbol_cap')
    if arm != 'RAW_SAFE' and total:
        if any(r > Decimal('.40')*total for r in by_sleeve.values()): errors.append('sleeve_share_cap')
        if abs(net) > Decimal('.60')*total: errors.append('net_direction_cap')
    return {**base, 'status': 'PROPOSED_PORTFOLIO_REJECT' if errors else 'PROPOSED_PORTFOLIO_FEASIBLE',
            'violations': errors, 'total_risk_usd': float(total), 'net_risk_usd': float(net),
            'sleeve_risk_usd': {k:float(v) for k,v in sorted(by_sleeve.items())},
            'scope': 'SUPPLIED_PROPOSAL_ONLY_NOT_AN_ALLOCATOR'}


def primitive_receipt(opportunity, stats, regime, vol, equity_usd):
    _require(_number(equity_usd) and equity_usd > 0, 'capital_unknown')
    s = score(opportunity, stats, regime, vol)
    arms = {}
    for arm in ARMS:
        multiplier = s.multiplier if arm == 'BRAIN_DET' else 1.
        risk = .005 * equity_usd * multiplier
        notional = risk / opportunity.stop_distance_frac
        _require(math.isfinite(risk) and math.isfinite(notional), 'sizing_numeric_overflow')
        arms[arm] = {'risk_usd':risk, 'notional_usd':notional, 'multiplier':multiplier,
                     'allocation_status':'NOT_ALLOCATED', 'ledger_mutated':False}
    result = {'schema':'BRAIN_V2_PRIMITIVE_RECEIPT_V1', 'status':'BLOCKED_DATA',
              'blocker':'FROZEN_WHOLE_BATCH_SUBSET_POLICY_AND_ACTUAL_STATS_VOL_SOURCE_REQUIRED',
              'opportunity':asdict(opportunity), 'opportunity_id':opportunity.id,
              'stats_input_sha256':digest(asdict(stats)), 'score':asdict(s),
              'arms':arms, 'equity_input_usd':equity_usd, 'regime':regime, 'vol':vol,
              'spec_sha256':SPEC_PIN, 'params_sha256':PARAMS_PIN,
              'orders_allowed':False, 'money_authority':False, 'portfolio_mutated':False}
    return {**result, 'sha256':digest(result)}


def verify_frozen_sources(manifest_path, *, root=None):
    root = Path(root or Path(__file__).resolve().parents[1])
    manifest = json.loads(Path(manifest_path).read_text())
    pins = {}
    for row in manifest['files']:
        path = root / row['snapshot_path']
        _require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'],
                 'frozen_snapshot_pin_mismatch')
        pins[row['source_path']] = row['sha256']
    _require(pins.get('research_lab/brain_v2/BRAIN_V2_RESEARCH_PREREG_V1.md') == SPEC_PIN
             and pins.get('research_lab/brain_v2/BRAIN_V2_PARAMS_V1.json') == PARAMS_PIN,
             'frozen_spec_or_parameters_mismatch')
    return {'verified_files':len(pins), 'research_commit':manifest['research_commit'],
            'orders_allowed':False, 'outcomes_read':False}
