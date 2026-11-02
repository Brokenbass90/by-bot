from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('role',['sports','clob','catalog'])
def test_public_data_units_have_no_financial_privileges_or_unbounded_resources(role):
    raw=(ROOT/'deploy/systemd'/('poly-ws-data-'+role+'.service')).read_text()
    for clause in ('DynamicUser=yes','ProtectHome=yes','ProtectSystem=strict','NoNewPrivileges=yes','CapabilityBoundingSet=','CPUQuota=10%','TasksMax=16','Slice=poly-ws-data.slice','RestartSec=60','--run-data-only','--role '+role):assert clause in raw
    assert 'RestartPreventExitStatus=78' not in raw and 'StartLimitIntervalSec=0' in raw
    assert 'EnvironmentFile=' not in raw and '/root/by-bot' not in raw
    assert 'MemoryMax=' in raw and 'ReadWritePaths=/var/lib/bybot-polydata-20261102' in raw

def test_slice_budget_covers_all_research_children():
    raw=(ROOT/'deploy/systemd/poly-ws-data.slice').read_text()
    assert 'CPUQuota=30%' in raw and 'MemoryMax=192M' in raw and 'TasksMax=48' in raw
