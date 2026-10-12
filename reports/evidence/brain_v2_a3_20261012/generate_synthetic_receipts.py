"""Synthetic A3/A4 protocol proof only; no market data, train generator or judge."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json

from research_lab.brain_v2_a3 import BrainJournal
from research_lab.brain_v2_frozen_primitives import canonical
from tests.test_brain_v2_a3_ticks import NOW, HOUR, TICK, op, init, tick, terminal


def main():
    first=op();second=op(1,sleeve='ETS2',tick=NOW+TICK)
    requests=[init(),tick([first]),tick([second],NOW+TICK),tick(at=NOW+2*TICK),
              tick(at=NOW+3*TICK),
              tick([op(tick=NOW+HOUR)],NOW+HOUR,
                   [terminal(first,expected=[NOW+HOUR],rates=[(NOW+HOUR,'.001')])]),
              tick([op(1,sleeve='ETS2',tick=NOW+HOUR+TICK)],NOW+HOUR+TICK,
                   [terminal(second,expected=[NOW+HOUR+TICK])])]
    with TemporaryDirectory(prefix='brain-a3-synthetic-') as directory:
        # macOS tempdir can contain /var -> /private/var; use its real owned
        # path, preserving the journal's refusal of symlinked runtime roots.
        root=Path(directory).resolve()/'journal'
        with BrainJournal(root) as journal:
            receipts=[journal.process(r) for r in requests]
        raw=(root/'journal.jsonl').read_bytes()
        with BrainJournal(root) as journal:
            reloaded=[journal.process(r) for r in requests]
            assert canonical(receipts)==canonical(reloaded)
            assert journal.state==receipts[-1]['state_after']
        assert (root/'journal.jsonl').read_bytes()==raw
    target=Path(__file__).resolve().parent
    (target/'synthetic_paired_receipts.json').write_bytes(canonical(receipts)+b'\n')
    proof=dict(schema='BRAIN_V2_A3_A4_SYNTHETIC_REPLAY_PROOF',authority='SYNTHETIC_ONLY_ORDERS_OFF',
               receipt_count=len(receipts),canonical_restart_exact=True,raw_journal_unchanged_on_replay=True,
               raw_journal_sha256=hashlib.sha256(raw).hexdigest(),raw_journal_bytes=len(raw),
               archive_sha256=hashlib.sha256(canonical(receipts)+b'\n').hexdigest(),
               unknown_pnl_is_null=True,unknown_risk_released=True,late_funding_recredit_allowed=False,
               funding_coverage=receipts[-1]['funding_coverage'],orders_allowed=False)
    (target/'synthetic_replay_proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({k:proof[k] for k in ('receipt_count','canonical_restart_exact','raw_journal_bytes','raw_journal_sha256')}))


if __name__=='__main__':main()
