import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_live_mode_cannot_fall_back_to_paper_credentials(tmp_path):
    env={k:v for k,v in os.environ.items() if not k.startswith('ALPACA_')}
    result=subprocess.run(['bash',str(ROOT/'scripts/run_alpaca_adaptive_paper.sh'),'--run-intended-live'],env=env,capture_output=True,text=True)
    assert result.returncode==2
    assert 'live_mode_requires_explicit_env' in result.stderr


def test_explicit_live_mode_does_not_source_legacy_hybrid_settings(tmp_path):
    env={k:v for k,v in os.environ.items() if not k.startswith('ALPACA_')}
    profile=tmp_path/'live.env';profile.write_text('ALPACA_BASE_URL=https://api.alpaca.markets\n')
    hybrid=tmp_path/'hybrid.env';hybrid.write_text('echo unexpected_hybrid >&2\nexit 66\n')
    python=tmp_path/'python';python.write_text('#!/bin/sh\nprintf "%s\\n" "$ALPACA_BASE_URL" "$ALPACA_SEND_ORDERS"\n');python.chmod(0o700)
    env.update(ALPACA_BASE_LOCAL_ENV=str(profile),ALPACA_PROTECTION_ENV=str(hybrid),ALPACA_PYTHON=str(python))
    result=subprocess.run(['bash',str(ROOT/'scripts/run_alpaca_adaptive_paper.sh'),'--run-intended-live'],env=env,capture_output=True,text=True)
    assert result.returncode==0, result.stderr
    assert result.stdout.splitlines()==['https://api.alpaca.markets','0']


def test_live_mode_rejects_paper_profile_before_python(tmp_path):
    env={k:v for k,v in os.environ.items() if not k.startswith('ALPACA_')}
    profile=tmp_path/'paper.env';profile.write_text('ALPACA_BASE_URL=https://paper-api.alpaca.markets\n')
    env.update(ALPACA_BASE_LOCAL_ENV=str(profile),ALPACA_PYTHON='/missing/python')
    result=subprocess.run(['bash',str(ROOT/'scripts/run_alpaca_adaptive_paper.sh'),'--preflight-intended-live'],env=env,capture_output=True,text=True)
    assert result.returncode==2
    assert 'live_mode_requires_exact_live_endpoint' in result.stderr
