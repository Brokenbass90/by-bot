import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('cron,process,expected', [
    ('*/30 * * * * bash /root/by-bot/scripts/run_alpaca_live_v38_once.sh', '', 9),
    ('*/15 * * * * bash /root/by-bot/scripts/run_alpaca_protective_exit_manager.sh', '', 9),
    ('# retired run_alpaca_live_v38_once.sh', 'bash /root/by-bot/scripts/run_alpaca_live_v38_once.sh', 9),
    ('# retired run_alpaca_live_v38_once.sh', '.venv/bin/python scripts/alpaca_protective_exit_manager.py', 9),
    ('# retired run_alpaca_live_v38_once.sh', '', 0),
])
def test_launcher_excludes_old_scheduled_and_running_writers(tmp_path, cron, process, expected):
    bins = tmp_path/'bin'; bins.mkdir()
    for name, output in [('crontab', cron), ('ps', process)]:
        executable = bins/name
        executable.write_text('#!/bin/sh\ncat <<\'EOF\'\n'+output+'\nEOF\n'); executable.chmod(0o700)
    python = bins/'python'; python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n'); python.chmod(0o700)
    profile = tmp_path/'live.env'; profile.write_text('ALPACA_BASE_URL=https://api.alpaca.markets\n')
    env = {k:v for k,v in os.environ.items() if not k.startswith('ALPACA_')}
    env.update(PATH=str(bins)+':'+env['PATH'], ALPACA_PYTHON=str(python),
        ALPACA_BASE_LOCAL_ENV=str(profile), ALPACA_INTENDED_RUNTIME=str(tmp_path/'runtime'), ALPACA_INTENDED_CACHE=str(tmp_path/'cache'))
    result = subprocess.run(['bash', str(ROOT/'scripts/run_alpaca_intended_live.sh'), '--send-orders'], env=env, capture_output=True, text=True)
    assert result.returncode == expected, result.stderr
    if expected == 0:
        assert '--send-orders' in result.stdout and '487.42' in result.stdout
    else:
        assert 'exclusive_owner_old_' in result.stderr and not result.stdout
