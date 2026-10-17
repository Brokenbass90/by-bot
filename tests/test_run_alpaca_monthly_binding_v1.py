import hashlib
import json
from pathlib import Path

from research_lab.alpaca_dynamic_v1 import digest
from research_lab.alpaca_monthly_binding_v1 import CONTRACT
from scripts import run_alpaca_monthly_binding_v1 as cli


def test_empty_manifest_must_not_claim_a_verified_runtime(tmp_path,capsys):
    value=dict(schema='ALPACA_MONTHLY_DISABLED_SOURCE_BINDING_V1',contract=CONTRACT,
        contract_sha256=digest(CONTRACT),files={},enabled=False,orders_allowed=False)
    p=tmp_path/'spec.json';p.write_text(json.dumps(value))
    assert cli.main(['--spec',str(p),'--spec-sha256',hashlib.sha256(p.read_bytes()).hexdigest()])==2
    assert 'MONTHLY_REQUIRED_SOURCE_MISSING' in capsys.readouterr().out
    assert not (cli.ROOT/'runtime/monthly-test').exists()


def test_money_flag_has_no_cli_route(tmp_path):
    import pytest
    with pytest.raises(SystemExit) as exc:
        cli.main(['--spec','unused','--spec-sha256','a'*64,'--apply'])
    assert exc.value.code==2
