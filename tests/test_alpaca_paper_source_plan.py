"""The maintenance CLI must recover a new attempt without adopting retired history."""
import copy
import sqlite3
import pytest
from test_alpaca_dynamic_v1 import api, policy, calendar, snapshot, ranking, book, NOW
from test_alpaca_expired_reservation_handoff import proof,fresh_next_week
from scripts import run_alpaca_dynamic_paper as cli


def next_attempt(book, snapshot, calendar, api, policy):
    old = book.propose(snapshot, calendar, NOW)
    later = NOW + 300000
    book.retire_undispatched(old['receipt_id'], proof(api, policy, old, later), later)
    fresh_next_week(book,snapshot,calendar)
    return old, book.propose(snapshot, calendar, snapshot['observed_ms'])


def test_exact_new_attempt_is_read_only_recoverable(book, snapshot, calendar, api, policy):
    old, new = next_attempt(book, snapshot, calendar, api, policy)
    before = book.path.read_bytes()
    assert cli.require_source_plan(book.path, new) == new
    assert book.path.read_bytes() == before
    with sqlite3.connect(book.path) as db:
        assert len(db.execute('SELECT * FROM intents').fetchall()) == 1
        assert len(db.execute('SELECT * FROM intent_attempts').fetchall()) == 1


def test_retired_plan_cannot_regain_cli_authority(book, snapshot, calendar, api, policy):
    old, _ = next_attempt(book, snapshot, calendar, api, policy)
    with pytest.raises(ValueError, match='PLAN_NOT_IN_SOURCE_BOOK'):
        cli.require_source_plan(book.path, old)


def test_changed_attempt_is_not_the_stored_plan(book, snapshot, calendar, api, policy):
    _, new = next_attempt(book, snapshot, calendar, api, policy)
    changed = copy.deepcopy(new)
    changed['qty'] = '999'
    with pytest.raises(ValueError, match='PLAN_NOT_IN_SOURCE_BOOK'):
        cli.require_source_plan(book.path, changed)


def test_duplicate_history_is_not_silently_deduplicated(book, snapshot, calendar, api, policy):
    old, new = next_attempt(book, snapshot, calendar, api, policy)
    with sqlite3.connect(book.path) as db:
        db.execute('UPDATE intent_attempts SET payload=?', (api.canonical(old).decode(),))
    with pytest.raises(ValueError, match='DUPLICATE_INTENT_RECEIPT'):
        cli.require_source_plan(book.path, new)


def test_missing_source_does_not_create_a_database(tmp_path):
    path = tmp_path / 'absent.sqlite'
    with pytest.raises(ValueError, match='SOURCE_BOOK_IDENTITY'):
        cli.require_source_plan(path, {})
    assert not path.exists()
