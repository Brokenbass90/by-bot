import json
from decimal import Decimal as D
from pathlib import Path

def test_all_84_native_protocol_paths_and_separate_sizing_blockers(tmp_path):
    from pump4_native_84_harness import run
    source=Path(__file__).parent/'fixtures/pump4_native_reference_84_20261026.json'
    result=run(tmp_path,source)
    assert result['cases']==result['protocol_pass']==84
    assert result['real_broker_writes']==result['real_broker_requests']==0
    assert result['financial_admission_pass_claimed'] is False
    assert sum(result['sizing_statuses'].values())==84
    assert all(r['unchanged_reference'] and D(r['entry_qty'])==D(r['tp1_qty'])+D(r['tp2_qty']) for r in result['rows'])
    (tmp_path/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
