import importlib,sqlite3,json,hashlib,copy
from pathlib import Path
import pytest
from tests.test_alpaca_dynamic_live_runtime_v1 import setup,case
from research_lab.alpaca_dynamic_v1 import canonical,digest

# Break caught: the approved envelope has no fresh source-plan -> intake assembler.
def test_assembly_module_exists_and_no_send_preserves_book(setup):
    try:m=importlib.import_module('research_lab.alpaca_first_entry_assembly_v1')
    except ImportError:m=None
    assert m is not None,'post-GO source-plan/intake assembler missing'
    _,_,intake,policy,binding,_=setup
    path=Path(binding['source_book']);before=path.read_bytes()
    result=m.preview_existing(intake,policy,binding,intake['prepared_ms'])
    assert result['status']=='FIRST_ENTRY_NO_SEND_READY',result
    assert path.read_bytes()==before
    assert result['broker_writes']==result['source_book_writes']==0
    assert not Path(binding['runtime']).exists()

@pytest.mark.parametrize('field,value',[('qty','1'),('symbol','META'),('session','2026-10-15')])
def test_changed_existing_intake_is_rejected_before_any_write(setup,field,value):
    m=importlib.import_module('research_lab.alpaca_first_entry_assembly_v1')
    _,_,intake,policy,binding,_=setup;bad=copy.deepcopy(intake);bad['plan'][field]=value
    before=Path(binding['source_book']).read_bytes()
    r=m.preview_existing(bad,policy,binding,intake['prepared_ms'])
    assert r['status']=='BLOCKED_DATA'
    assert Path(binding['source_book']).read_bytes()==before
