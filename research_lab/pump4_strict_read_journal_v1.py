"""PUMP DATA-only full-chain parser, no cache or changed write semantics.

Every byte/row/event/hash is still verified under the inherited original lock.
The existing writer, Python-event validation and fsync are inherited unchanged.
Only the already-decoded event avoids a redundant JSON roundtrip and encoding.
A versioned DATA bootstrap must inject this class only into Pump4Intake.
"""
import hashlib
import json
import os
from research_lab.att1_lifecycle_journal import (
    LifecycleJournal,JournalViolation,GENESIS,SCHEMA,_canonical,_hash,_pairs,_constant,
)

class Pump4StrictReadJournal(LifecycleJournal):
    def _load(self, fd: int | None):
        if fd is None:
            return [], {}, GENESIS, 0
        size = os.fstat(fd).st_size
        if size > self.max_bytes:
            raise JournalViolation('journal size limit')
        os.lseek(fd, 0, os.SEEK_SET)
        chunks, total = [], 0
        while True:
            chunk = os.read(fd, min(65536, self.max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > self.max_bytes:
                raise JournalViolation('journal size limit')
            chunks.append(chunk)
        raw = b''.join(chunks)
        if len(raw) != size:
            raise JournalViolation('journal size changed while locked')
        if raw and not raw.endswith(b'\n'):
            raise JournalViolation('truncated journal')
        events, identities, tip = [], {}, GENESIS
        for seq, line in enumerate(raw.splitlines(), 1):
            if len(line) + 1 > self.max_record_bytes:
                raise JournalViolation('record size limit')
            try:
                row = json.loads(line.decode('ascii'), object_pairs_hook=_pairs, parse_constant=_constant)
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise JournalViolation('invalid journal JSON') from exc
            if not isinstance(row, dict) or set(row) != {'seq', 'prev_hash', 'event', 'event_sha256', 'hash'}:
                raise JournalViolation('invalid row schema')
            if type(row['seq']) is not int or row['seq'] != seq or row['prev_hash'] != tip:
                raise JournalViolation('sequence/hash chain mismatch')
            # The strict parser above already produced a fresh JSON-native
            # object. Python append inputs still use the original _event.
            value = row['event']
            if not isinstance(value, dict):
                raise JournalViolation('event must be a JSON object')
            eid = value.get('event_id')
            if value.get('schema_id') != SCHEMA or not isinstance(eid, str) or not 1 <= len(eid) <= 256:
                raise JournalViolation('invalid event identity/schema')
            event_bytes = _canonical(value)
            digest = hashlib.sha256(event_bytes).hexdigest()
            core = {key: val for key, val in row.items() if key != 'hash'}
            if row['event_sha256'] != digest or row['hash'] != _hash(core) or line != _canonical(row):
                raise JournalViolation('event/row hash or canonical bytes mismatch')
            if value['event_id'] in identities:
                raise JournalViolation('duplicate event persisted')
            events.append(value)
            identities[value['event_id']] = event_bytes
            tip = row['hash']
        return events, identities, tip, size

