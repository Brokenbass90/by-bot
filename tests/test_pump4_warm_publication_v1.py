"""Normal warm publication reuses the frozen locked journal validator."""
import json
from pathlib import Path
import pytest
from research_lab.pump4_supervisor_v1 import Supervisor
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
from test_pump4_supervisor_v1 import archive,archive_bars
from test_pump4_stream_publication_v1 import warm
from test_pump4_bybit_sources_v1 import NOW,H


class Baseline(Supervisor):
    @staticmethod
    def _warm_accept(intake,bar,*,available_ms,observed_ms):
        result=intake.accept(bar,available_ms=available_ms,observed_ms=observed_ms)
        return result,intake.snapshot()['cursor_ms']


def setup(home,kind,cls=Supervisor):
    root=home/'state'
    if kind in ('signal','cooldown'):
        source=warm(root,home);at=NOW
        if kind=='cooldown':
            cls(root,clock=lambda:NOW+3).process_archive(source)
            row=json.loads((source/'symbols/ZROUSDT.json').read_bytes())
            bytime={int(b[0]):[int(b[0]),*map(float,b[1:6])] for cap in row['captures'] for b in cap['body']['result']['list']}
            bars=[bytime[t] for t in sorted(bytime)];bars.append([NOW+H,100.,100.,100.,100.,0.])
            source=archive_bars(home/'later',bars[-1002:]);at=NOW+H
    else:
        cls(root,clock=lambda:NOW+3).process_archive(archive(home/'first'))
        source=archive(home/'later',hour=2001);at=NOW+H
    row=json.loads((source/'symbols/ZROUSDT.json').read_bytes())
    header=json.loads((source/'receipt.json').read_bytes())
    return root,row,header,cls(root,clock=lambda:at+3)


@pytest.mark.parametrize('kind',['plain','signal','cooldown'])
def test_warm_result_and_journal_equal_frozen_accept_path(tmp_path,kind):
    outputs=[]
    for name,cls in [('baseline',Baseline),('fast',Supervisor)]:
        home=tmp_path/name;home.mkdir();root,row,header,s=setup(home,kind,cls)
        result=s._symbol('ZROUSDT',row,header,'same-recorded-archive')
        outputs.append((result,(root/'intake/ZROUSDT.jsonl').read_bytes(),
            {p.name:p.read_bytes() for p in (root/'observations').glob('*.json')}))
    assert outputs[0]==outputs[1]
    if kind=='signal':assert outputs[1][0]['decisions'][0]['status']=='CAUSAL_PLAN_DATA_ONLY'
    if kind=='cooldown':assert outputs[1][0]['decisions'][0]['decision']['cooldown_remaining']>0


def test_plain_warm_path_runs_two_frozen_replays_not_four(tmp_path,monkeypatch):
    root,row,header,s=setup(tmp_path,'plain');original=Pump4Intake._replay;calls=[]
    def counted(self,events):calls.append(len(events));return original(self,events)
    monkeypatch.setattr(Pump4Intake,'_replay',counted)
    out=s._symbol('ZROUSDT',row,header,'one-warm-bar')
    assert out['mode']=='CURRENT_CLOSED_BAR' and len(calls)==2


def test_crash_after_batch_keeps_existing_recovery_and_no_promotion(tmp_path,monkeypatch):
    root,row,header,s=setup(tmp_path,'signal')
    def lost(*a,**kw):raise OSError('before locked append')
    monkeypatch.setattr(Supervisor,'_warm_accept',staticmethod(lost))
    with pytest.raises(OSError):s._symbol('ZROUSDT',row,header,'crash')
    # Existing immutable batch marks recovery; it must use frozen accept instead.
    out=s._symbol('ZROUSDT',row,header,'crash')
    assert out['decisions'][0]['mode']=='RECOVERY_REPLAY'
    assert out['decisions'][0]['status']=='REPLAY_NOT_PROSPECTIVE'


def test_locked_replay_selects_requested_duplicate_before_later_bar(tmp_path):
    root,row,header,s=setup(tmp_path,'plain');i=Pump4Intake(root/'intake/ZROUSDT.jsonl','ZROUSDT')
    bar=row['source']['signal_bar'];kw=dict(available_ms=row['source']['available_ms'],observed_ms=row['source']['observed_ms'])
    requested=i.accept(bar,**kw)['decision']
    later=[bar[0]+H,*bar[1:]];i.accept(later,available_ms=bar[0]+2*H,observed_ms=bar[0]+2*H)
    result,cursor=s._warm_accept(i,bar,**kw)
    assert result==dict(new=False,decision=requested) and cursor==later[0]
    with pytest.raises(ValueError):s._warm_accept(i,bar,available_ms=kw['available_ms'],observed_ms=kw['observed_ms']+1)
