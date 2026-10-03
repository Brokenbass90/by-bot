from __future__ import annotations

import hashlib
from pathlib import Path

from bot import ai_context_brief as brief


def test_operations_evidence_is_bounded_source_cited_and_snapshot_only(tmp_path):
    folder=tmp_path/'reports';folder.mkdir()
    raw=b'# Current production\nAlpaca LIVE; ATT1 NEW orders OFF\n'+b'old history\n'*5000
    (folder/'MASTER_HANDOFF.md').write_bytes(raw)
    result=brief.operations_evidence_context(tmp_path,max_chars=1800)
    assert len(result)<=1800
    assert 'Alpaca LIVE; ATT1 NEW orders OFF' in result
    assert hashlib.sha256(raw).hexdigest() in result
    assert 'reports/MASTER_HANDOFF.md' in result
    assert 'PROJECT_SNAPSHOT_NOT_BROKER_TRUTH' in result


def test_operations_evidence_reads_only_allowlisted_documents(tmp_path):
    (tmp_path/'reports').mkdir()
    (tmp_path/'.env').write_text('API_KEY=TOP_SECRET')
    (tmp_path/'reports'/'random.md').write_text('TOP_SECRET')
    result=brief.operations_evidence_context(tmp_path)
    assert 'TOP_SECRET' not in result
    assert 'NOT_CONFIRMED' in result


def test_operations_evidence_rejects_symlink_escape(tmp_path):
    (tmp_path/'reports').mkdir()
    secret=tmp_path/'secret';secret.write_text('DO_NOT_SEND')
    (tmp_path/'reports'/'MASTER_HANDOFF.md').symlink_to(secret)
    result=brief.operations_evidence_context(tmp_path)
    assert 'DO_NOT_SEND' not in result
    assert 'NOT_CONFIRMED' in result


def test_operations_evidence_rejects_symlinked_parent(tmp_path):
    outside=tmp_path/'outside';outside.mkdir()
    (outside/'MASTER_HANDOFF.md').write_text('DO_NOT_SEND')
    (tmp_path/'reports').symlink_to(outside,target_is_directory=True)
    assert 'DO_NOT_SEND' not in brief.operations_evidence_context(tmp_path)


def test_operations_evidence_reflects_file_change_without_chat_reset(tmp_path):
    (tmp_path/'reports').mkdir()
    p=tmp_path/'reports'/'MASTER_HANDOFF.md';p.write_text('OLD_SNAPSHOT')
    a=brief.operations_evidence_context(tmp_path)
    p.write_text('NEW_ORDERS_OFF')
    b=brief.operations_evidence_context(tmp_path)
    assert 'NEW_ORDERS_OFF' in b and 'OLD_SNAPSHOT' not in b
    assert a!=b
