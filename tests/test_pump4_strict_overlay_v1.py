import hashlib,importlib.util,json,sys
from pathlib import Path
import pytest
from research_lab import pump4_closed_bar_intake_v1 as intake,att1_lifecycle_journal as journal

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'reports/evidence/pump4_strict_read_20261103/bootstrap.py'
def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,x):p.write_bytes(json.dumps(x,sort_keys=True).encode())

def fixture(tmp_path,monkeypatch):
 p=tmp_path/'overlay';b=tmp_path/'base';p.mkdir();b.mkdir()
 (p/'pump4_strict_read_journal_v1.py').write_bytes((ROOT/'research_lab/pump4_strict_read_journal_v1.py').read_bytes())
 (b/'bootstrap.py').write_text('raise AssertionError("intercept required")\n')
 original=dict(material_sha256='7d8ae05dab162ec5eaded17a7ed779c14d092880553dcd96345cf3d3198e6cf0',files={n:sha((ROOT/n).read_bytes()) for n in ['research_lab/att1_lifecycle_journal.py','research_lab/pump4_closed_bar_intake_v1.py']})
 write(b/'original-manifest.json',original)
 write(b/'patch-manifest.json',dict(original_app=str(ROOT),files={n:sha((b/n).read_bytes()) for n in ['bootstrap.py','original-manifest.json']}))
 m=dict(schema='PUMP4_STRICT_READ_OVERLAY_V1',base_patch=str(b),base_patch_sha256=sha((b/'patch-manifest.json').read_bytes()),files={'pump4_strict_read_journal_v1.py':sha((p/'pump4_strict_read_journal_v1.py').read_bytes())},orders_allowed=False,financial_authority=False)
 write(p/'patch-manifest.json',m)
 spec=importlib.util.spec_from_file_location('strict_overlay_test',SCRIPT);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 monkeypatch.setattr(intake,'LifecycleJournal',journal.LifecycleJournal);monkeypatch.setattr(sys,'path',list(sys.path));monkeypatch.setattr(sys,'argv',list(sys.argv))
 return p,b,m,module


def test_overlay_only_binds_data_intake_and_delegates_frozen_bootstrap(tmp_path,monkeypatch):
 p,b,m,module=fixture(tmp_path,monkeypatch);seen=[]
 def intercepted(path,run_name):
  assert intake.LifecycleJournal is not journal.LifecycleJournal
  assert intake.LifecycleJournal._append is journal.LifecycleJournal._append
  assert intake.LifecycleJournal._locked is journal.LifecycleJournal._locked
  assert intake.LifecycleJournal.__module__=='research_lab.pump4_strict_read_journal_v1'
  seen.append((path,run_name,list(sys.argv)))
 monkeypatch.setattr(module.runpy,'run_path',intercepted)
 module.run(p,sha((p/'patch-manifest.json').read_bytes()),['--root','unchanged','--run'])
 assert seen==[(str(b/'bootstrap.py'),'__main__',[str(b/'bootstrap.py'),'--patch-manifest-sha256',m['base_patch_sha256'],'--root','unchanged','--run'])]


@pytest.mark.parametrize('fault',['manifest','parser','base','path'])
def test_overlay_drift_never_imports_or_runs_candidate(tmp_path,monkeypatch,fault):
 p,b,m,module=fixture(tmp_path,monkeypatch);pin=sha((p/'patch-manifest.json').read_bytes());seen=[]
 monkeypatch.setattr(module.runpy,'run_path',lambda *a,**k:seen.append(a))
 if fault=='manifest':pin='0'*64
 if fault=='parser':(p/'pump4_strict_read_journal_v1.py').write_text('raise RuntimeError("must not import")')
 if fault=='base':(b/'bootstrap.py').write_text('changed')
 if fault=='path':
  m['files']={'../escape':'0'*64};write(p/'patch-manifest.json',m);pin=sha((p/'patch-manifest.json').read_bytes())
 with pytest.raises(ValueError):module.run(p,pin,[])
 assert not seen and intake.LifecycleJournal is journal.LifecycleJournal
