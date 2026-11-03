import json,hashlib,copy
from dataclasses import asdict
from pathlib import Path
from research_lab import alpaca_monthly_binding_v1 as b
from scripts.run_alpaca_dynamic_v1_orders_off import load_history
import pytest

def fixture(tmp_path):
 history={'LLY':[dict(session='2026-10-30',open=100.,high=102.,low=98.,close=101.)]}
 bars=load_history(history);causal={s:[{**asdict(x),'session_date':x.session_date.isoformat()} for x in rows] for s,rows in bars.items()}
 original=dict(signal_session='2026-10-30',source_sha256='a'*64,source_available_ms=1793391679076,causal_history_sha256=b.digest(causal))
 doc=dict(schema='MONTHLY_INITIAL_RECOVERY_FROZEN_HISTORY_V1',original_selection_sha256=b.digest(original),source_sha256=original['source_sha256'],source_available_ms=original['source_available_ms'],history=history)
 p=tmp_path/'frozen-history.json';p.write_text(json.dumps(doc));policy=dict(frozen_history=dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
 return original,policy,p

def test_exact_bytes_reuse_validation_not_mutable_history(tmp_path,monkeypatch):
 original,policy,p=fixture(tmp_path);b._recovery_history_document.cache_clear();fn=b.asdict;calls=[]
 def counted(x):calls.append(1);return fn(x)
 monkeypatch.setattr(b,'asdict',counted)
 first=b.initial_recovery_history(policy,original);n=len(calls);assert n>0
 first['LLY'].clear()
 second=b.initial_recovery_history(policy,original)
 assert len(second['LLY'])==1 and len(calls)==n
 assert b._recovery_history_document.cache_info().hits>=1

@pytest.mark.parametrize('fault',['file','provenance','expected_causal'])
def test_cached_bytes_never_bypass_live_pin_or_original_provenance(tmp_path,fault):
 original,policy,p=fixture(tmp_path);b.initial_recovery_history(policy,original)
 if fault=='file':p.write_text(p.read_text()+' ')
 elif fault=='provenance':original['source_available_ms']+=1
 else:original['causal_history_sha256']='f'*64
 with pytest.raises(ValueError):b.initial_recovery_history(policy,original)


def test_shared_bar_values_are_frozen_and_only_containers_are_copied(tmp_path):
 from dataclasses import FrozenInstanceError
 original,policy,p=fixture(tmp_path);first=b.initial_recovery_history(policy,original);second=b.initial_recovery_history(policy,original)
 assert first is not second and first['LLY'] is not second['LLY']
 assert first['LLY'][0] is second['LLY'][0]
 with pytest.raises(FrozenInstanceError):first['LLY'][0].close=0
 assert second['LLY'][0].close==101.
