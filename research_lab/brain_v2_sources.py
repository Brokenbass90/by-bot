"""Manifest-bound historical Brain adapters; no judge, broker or order path.

Entry projection cannot expose R/actual hold. Terminal projection is separate
and gated to its A3 release tick. Historical close times are model availability,
not measured publication. Funding pairs alone cannot certify a complete calendar
or timely publication and therefore do not become KNOWN funding evidence.
"""
from __future__ import annotations

from bisect import bisect_right
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
from types import MappingProxyType

import numpy as np

from research_lab.brain_v2_frozen_primitives import (
    BrainBlocked, Opportunity, RegimeBar, HOUR, DEVELOP_END_EXCLUSIVE_MS,
    digest, _identity, _number, _pin, _require, _time,
)
from research_lab.brain_v2_a1 import BAR_MS, build_contexts, signal_available_ms
from research_lab.brain_v2_a3 import COST_MODEL
from research_lab.os2_shadow_journal import strict_json

MAX_HOLD = MappingProxyType(dict(ATT1=336, SBR1=168, ASR1=168,
                               ETS2=168, SF3=336, BOUNCE1=48))


def _relative(path):
    _require(isinstance(path, str) and bool(path) and not path.startswith('/')
             and all(p not in ('', '.', '..') for p in path.split('/'))
             and '\\' not in path, 'source_path')
    return path


def _json(raw, reason):
    try:
        return strict_json(raw)
    except (TypeError, ValueError, UnicodeError) as error:
        raise BrainBlocked(reason) from error


def _develop_window(start, end):
    _require(_time(start) and _time(end) and start < end
             and end <= DEVELOP_END_EXCLUSIVE_MS, 'develop_window')


class PinnedSources:
    """Pin passed by caller must already be published, never inferred from bytes."""

    def __init__(self, root, manifest_raw, *, expected_manifest_sha256):
        m = _json(manifest_raw, 'manifest_json')
        _require(isinstance(m, dict) and _pin(expected_manifest_sha256)
                 and m.get('sha256') == expected_manifest_sha256
                 and digest({k:v for k,v in m.items() if k != 'sha256'}) == expected_manifest_sha256,
                 'manifest_pin')
        _require(m.get('schema') in ('BRAIN_V2_DEVELOP_INPUT_MANIFEST',
                                    'BRAIN_V2_DEVELOP_SOURCE_MANIFEST')
                 and m.get('orders_allowed') is False and isinstance(m.get('files'), list),
                 'manifest_contract')
        root = Path(root)
        _require(root.is_dir() and not root.is_symlink(), 'source_root')
        self.root = root.resolve()
        self.manifest_sha256 = expected_manifest_sha256
        rows = {}
        for row in m['files']:
            _require(isinstance(row, dict), 'manifest_row')
            name = _relative(row.get('path'))
            _require(name not in rows and _pin(row.get('sha256'))
                     and type(row.get('bytes')) is int and 0 <= row['bytes'] <= 256_000_000
                     and isinstance(row.get('role'), str), 'manifest_row_identity')
            rows[name] = MappingProxyType(deepcopy(row))
        self.rows = MappingProxyType(rows)

    def read(self, name):
        _relative(name)
        _require(name in self.rows, 'source_not_manifested')
        path = self.root
        for part in name.split('/'):
            path = path / part
            _require(not path.is_symlink(), 'source_symlink')
        row = self.rows[name]
        try:
            _require(path.is_file() and path.stat().st_size == row['bytes'], 'source_bytes_or_hash')
            raw = path.read_bytes()
        except OSError as error:
            raise BrainBlocked('source_read') from error
        _require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
                 'source_bytes_or_hash')
        return raw

    def verify(self):
        for name in self.rows:
            self.read(name)
        return dict(manifest_sha256=self.manifest_sha256, file_count=len(self.rows),
                    integrity='PASS', orders_allowed=False)

    def stream(self, name, *, sleeves):
        _require(self.rows.get(name, {}).get('role') in ('stream','trade_stream'), 'stream_role')
        return StreamArchive(self.read(name), self.rows[name]['sha256'], sleeves)

    def h1(self, name):
        _require(self.rows.get(name, {}).get('role') in ('h1','h1_bars'), 'h1_role')
        return H1Archive(self.read(name), self.rows[name]['sha256'])

    def funding(self, name, *, symbol):
        _require(self.rows.get(name, {}).get('role') == 'funding', 'funding_role')
        return FundingArchive(self.read(name), self.rows[name]['sha256'], symbol)

    def contexts(self, entries, *, hour_ms, btc_path, h1_paths):
        """Reuse frozen context math; absent symbol history stays UNKNOWN.

        Every supplied file must match its manifest. This supplies historical
        closed-bar envelopes only, never asserts current feed/broker freshness.
        """
        btc = self.h1(btc_path) if btc_path is not None else None
        symbols = {}
        for symbol in {entry.opportunity.symbol for entry in entries}:
            if symbol in h1_paths:
                archive = self.h1(h1_paths[symbol])
                symbols[symbol] = dict(bars=archive.closed(hour_ms), source_hash=archive.source_hash)
        return build_contexts([entry.opportunity for entry in entries], hour_ms=hour_ms,
                              btc_h4=None if btc is None else dict(
                                  bars=btc.h4_closed(hour_ms), source_hash=btc.source_hash),
                              symbol_h1=symbols)


@dataclass(frozen=True)
class EntryProjection:
    opportunity: Opportunity
    lev: float
    availability_basis: str = 'FROZEN_A2_A3_HISTORICAL_MODEL'

    @property
    def metadata(self):
        return MappingProxyType(dict(lev=self.lev, source_hash=self.opportunity.source_hash,
                                     t_available=self.opportunity.t_available, entry_rule='next_open'))


class StreamArchive:
    def __init__(self, raw, source_hash, sleeves):
        _require(type(sleeves) is tuple and len(set(sleeves)) == len(sleeves)
                 and all(s in BAR_MS for s in sleeves), 'stream_sleeves')
        data = _json(raw, 'stream_json')
        _require(isinstance(data, list), 'stream_schema')
        self.source_hash = source_hash
        self._entries, self._terminals = {}, {}
        seen = set()
        for row in data:
            _require(isinstance(row, dict) and {'leg','sym','side','ts','lev','R','hours'} <= set(row)
                     and set(row) <= {'leg','sym','side','ts','lev','R','hours','reg'}, 'stream_row')
            sleeve, ts, lev = row['leg'], row['ts'], row['lev']
            _require(isinstance(sleeve,str) and sleeve in BAR_MS and _identity(row['sym'])
                     and _time(ts) and ts % BAR_MS[sleeve] == 0
                     and _number(lev) and lev > 0 and row['side'] in ('long','short'), 'stream_entry')
            key = (sleeve, row['sym'], row['side'], ts)
            _require(key not in seen, 'stream_duplicate_identity')
            seen.add(key)
            if sleeve not in sleeves:
                continue
            op = Opportunity(sleeve,row['sym'],row['side'],ts,signal_available_ms(sleeve,ts),
                             'next_open',1 / lev,MAX_HOLD[sleeve],COST_MODEL,source_hash)
            self._entries[op.id] = EntryProjection(op, lev)
            # Retained privately, never part of entry/ranking/sizing envelopes.
            self._terminals[op.id] = (row['hours'], row['R'])

    def entries(self, *, start_ms, end_ms):
        _develop_window(start_ms, end_ms)
        return tuple(sorted((entry for entry in self._entries.values()
                             if start_ms <= entry.opportunity.t_available < end_ms),
                            key=lambda x:(x.opportunity.t_available,x.opportunity.id)))

    def terminal(self, opportunity_id, *, tick_ms, funding):
        """A3 modeled release; caller must separately certify funding coverage.

        This method is not used on developing outcomes before a frozen run gate.
        No earlier R/actual-hours envelope or later retroactive cash adjustment.
        """
        _require(opportunity_id in self._entries, 'terminal_unknown_identity')
        entry = self._entries[opportunity_id]
        hours, R = self._terminals[opportunity_id]
        _require(type(hours) is int and 1 <= hours <= entry.opportunity.max_hold_h, 'terminal_hours')
        release = entry.opportunity.t_available + hours * HOUR
        _require(_time(tick_ms) and tick_ms == release, 'terminal_not_release_tick')
        _require(release < DEVELOP_END_EXCLUSIVE_MS, 'terminal_outside_develop')
        _require(_number(R) and isinstance(funding, dict), 'terminal_outcome_or_funding')
        return dict(opportunity_id=opportunity_id,hours=hours,R=R,available_ms=release,
                    source_hash=self.source_hash,cost_model_id=COST_MODEL,funding=deepcopy(funding))


class H1Archive:
    publication_basis = 'HISTORICAL_CLOSE_MODEL_NOT_FEED_TIMESTAMP'

    def __init__(self, raw, source_hash):
        self.source_hash = source_hash
        try:
            with np.load(io.BytesIO(raw), allow_pickle=False) as data:
                _require({'ts','ohlcv','nsub'} <= set(data.files), 'h1_schema')
                ts, prices, nsub = data['ts'], data['ohlcv'], data['nsub']
                _require(ts.ndim == 1 and ts.dtype.kind in 'iu' and prices.shape == (len(ts),5)
                         and nsub.shape == ts.shape and nsub.dtype.kind in 'iu', 'h1_shape')
                _require(np.all(nsub >= 0) and np.all(nsub <= 12), 'h1_subbar_count')
                self.incomplete_subbar_count = int(np.count_nonzero(nsub != 12))
                bars = []
                for i, (t, p) in enumerate(zip(ts,prices)):
                    t = int(t)
                    _require(_time(t) and t % HOUR == 0 and (not i or t > int(ts[i-1]))
                             and np.isfinite(p).all() and min(p[:4]) > 0 and p[4] >= 0
                             and p[2] <= min(p[0],p[3]) <= max(p[0],p[3]) <= p[1], 'h1_bar')
                    bars.append(RegimeBar(t,*map(float,p),t+HOUR))
        except (ValueError, KeyError, TypeError, OSError) as error:
            raise BrainBlocked('h1_archive') from error
        self._bars = tuple(bars)
        self._closes = tuple(b.available_ms for b in bars)

    def closed(self, hour_ms):
        _require(_time(hour_ms) and hour_ms % HOUR == 0
                 and hour_ms <= DEVELOP_END_EXCLUSIVE_MS, 'h1_develop_cutoff')
        return self._bars[:bisect_right(self._closes, hour_ms)]

    def h4_closed(self, hour_ms):
        # Identical UTC grouping to frozen rezhim_v1.agg4h; no subbar repair.
        groups = {}
        for b in self.closed(hour_ms):
            groups.setdefault(b.open_ms//(4*HOUR)*(4*HOUR), []).append(b)
        result = []
        for start, children in groups.items():
            if len(children) != 4 or [b.open_ms for b in children] != [start+i*HOUR for i in range(4)]:
                continue
            result.append(RegimeBar(start,children[0].o,max(b.h for b in children),
                                    min(b.l for b in children),children[-1].c,
                                    sum(b.v for b in children),start+4*HOUR))
        return tuple(result)


class FundingArchive:
    """Actual archived rates, with missing calendar/publication kept explicit."""

    def __init__(self, raw, source_hash, symbol):
        data = _json(raw, 'funding_json')
        _require(isinstance(data,dict) and data.get('symbol') == symbol
                 and isinstance(data.get('funding'),list), 'funding_symbol_or_schema')
        rows = []
        for row in data['funding']:
            _require(isinstance(row,list) and len(row) == 2 and _time(row[0])
                     and _number(row[1]) and (not rows or row[0] > rows[-1][0]),
                     'funding_duplicate_unordered_or_nonfinite')
            rows.append(tuple(row))
        self._rows = tuple(rows)
        self.source_hash, self.symbol = source_hash, symbol

    def coverage(self, *, start_ms, end_ms):
        _develop_window(start_ms,end_ms)
        count = sum(start_ms < t <= end_ms for t,_ in self._rows)
        return dict(status='BLOCKED_DATA',reason='funding_calendar_and_publication_unbound',
                    symbol=self.symbol,source_hash=self.source_hash,start_ms=start_ms,end_ms=end_ms,
                    archive_event_count=count,calendar_status='UNKNOWN',publication_status='UNKNOWN',
                    rate_sum=None,orders_allowed=False)
