import pytest
from research_lab.kity_micro_transport_v1 import SourceError


def test_handoff_rejects_nonflat_or_incomplete_account_before_mutation():
    from research_lab.kity_micro_handoff_v1 import require_flat
    with pytest.raises(SourceError):require_flat([dict(symbol='LTCUSDT',size='.1')],[])
    with pytest.raises(SourceError):require_flat([], [dict(orderId='foreign')])
    with pytest.raises(SourceError):require_flat([dict(size='NaN')],[])
    assert require_flat([],[]) is None


def test_rollback_never_returns_writer_while_send_uncertain_or_native_active():
    from research_lab.kity_micro_handoff_v1 import rollback_safe
    s=dict(held={'LTCUSDT':'0'},entries={},exits={},ownership_conflict=False,broker_flat_proven=True)
    assert rollback_safe(s)
    s['entries']={'LTCUSDT':dict(terminal=False,filled='0',terminal_quantity=None)}
    assert not rollback_safe(s)
    s['entries']={};s['exits']={'SL':dict(terminal=False,filled='0',terminal_quantity=None,is_native_protection=True)}
    assert not rollback_safe(s)


def test_rollback_does_not_require_research_or_closed_trade_profit():
    from research_lab.kity_micro_handoff_v1 import rollback_safe
    s=dict(held={'LTCUSDT':'0'},entries={'LTCUSDT':dict(terminal=True,filled='1',terminal_quantity='1')},
        exits={'X':dict(terminal=True,filled='1',terminal_quantity='1')},ownership_conflict=False,broker_flat_proven=True)
    assert rollback_safe(s)
