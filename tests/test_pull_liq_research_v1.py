import pytest
from scripts import pull_liq_research_v1 as cli


def test_default_does_not_connect_or_write(monkeypatch,capsys):
    monkeypatch.setattr(cli.subprocess,'run',lambda *a,**k:pytest.fail('no network expected'))
    assert cli.main([])==0 and 'NO_NETWORK_DATA_ONLY' in capsys.readouterr().out


@pytest.mark.parametrize('args',[['--pull'],['--pull','--day','../../escape']])
def test_missing_paths_or_untrusted_filename_cannot_connect(monkeypatch,capsys,args):
    monkeypatch.setattr(cli.subprocess,'run',lambda *a,**k:pytest.fail('no network expected'))
    assert cli.main(args)==2 and 'BLOCKED_DATA_PULL' in capsys.readouterr().out
