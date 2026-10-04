"""An opted-in OLD process cannot regain entry authority through damaged controls."""
import json
import os
import subprocess
import sys

import pytest


def child(tmp_path, *, retirement, content=None):
    path = tmp_path / 'controls.json'
    if content is not None:
        path.write_text(content)
    env = {**os.environ}
    if retirement is None:
        env.pop('ATT1_ENTRY_RETIRED', None)
    else:
        env['ATT1_ENTRY_RETIRED'] = retirement
    code = '''
import json,os,sys
from pathlib import Path
from bot.operator_strategy_controls import is_paused,snapshot,resume,format_status,OperatorControlError
p=Path(sys.argv[1])
before=is_paused('att1',path=p)
# A later overlay/config edit must not change a process-start retirement decision.
os.environ['ATT1_ENTRY_RETIRED']='0'
os.environ['ENABLE_ATT1_TRADING']='1'
after=is_paused('att1_trendline_touch',path=p)
state=snapshot(p)
status=format_status(p)
try:
 resume('att1',path=p)
except OperatorControlError:
 resumed=False
else:
 resumed=True
print(json.dumps({'before':before,'after':after,'state':state,'resume_allowed':resumed,
                 'status':status,
                 'range_paused':is_paused('range',path=p)}))
'''
    result = subprocess.run([sys.executable, '-c', code, str(path)], env=env,
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


@pytest.mark.parametrize('content', [None, '{broken', '{}',
    '{"schema_id":"operator_strategy_controls_v1","paused":{}}',
    '{"schema_id":"operator_strategy_controls_v1","paused":{"att1":{"scope":"new_entries_only"}}}'])
def test_retired_process_denies_att1_after_damage_reload_and_resume(tmp_path, content):
    out = child(tmp_path, retirement='1', content=content)
    assert out['before'] is True
    assert out['after'] is True
    assert out['resume_allowed'] is False
    assert out['state']['retired_sleeves'] == ['att1']
    assert 'att1' in out['state']['paused_sleeves']
    assert out['state']['retirement_source'] == 'process_start_environment'
    assert 'Retired new entries: att1' in out['status']
    if content in ('{broken', '{}'):
        assert out['state']['read_error']
    assert out['range_paused'] is False


@pytest.mark.parametrize('flag', ['', 'garbled', 'true'])
def test_present_invalid_retirement_flag_fails_closed_for_att1_only(tmp_path, flag):
    out = child(tmp_path, retirement=flag)
    assert out['before'] is True
    assert out['after'] is True
    assert out['range_paused'] is False


@pytest.mark.parametrize('flag', [None, '0'])
def test_unretired_process_preserves_legacy_pause_semantics(tmp_path, flag):
    out = child(tmp_path, retirement=flag)
    assert out['before'] is False
    assert out['after'] is False
    assert out['resume_allowed'] is True
    assert out['state']['retired_sleeves'] == []
