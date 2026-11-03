"""Versioned PUMP4 DATA-only strict-read overlay; no financial entrypoint."""
import argparse,hashlib,importlib.util,json,pathlib,runpy,sys

def sha(raw):return hashlib.sha256(raw).hexdigest()
def checked(root,files):
 for name,pin in files.items():
  rel=pathlib.PurePosixPath(name)
  if rel.is_absolute() or '..' in rel.parts:raise ValueError('OVERLAY_UNSAFE_PATH')
  path=root/name
  if path.is_symlink() or sha(path.read_bytes())!=pin:raise ValueError('OVERLAY_FILE_PIN')

def run(folder,pin,remaining):
 folder=pathlib.Path(folder);raw=(folder/'patch-manifest.json').read_bytes()
 if sha(raw)!=pin:raise ValueError('OVERLAY_MANIFEST_PIN')
 m=json.loads(raw)
 if m['schema']!='PUMP4_STRICT_READ_OVERLAY_V1' or m['orders_allowed'] is not False or m['financial_authority'] is not False:raise ValueError('OVERLAY_SCOPE')
 checked(folder,m['files']);base=pathlib.Path(m['base_patch']);base_raw=(base/'patch-manifest.json').read_bytes()
 if sha(base_raw)!=m['base_patch_sha256']:raise ValueError('BASE_MANIFEST_PIN')
 b=json.loads(base_raw);checked(base,b['files']);old=pathlib.Path(b['original_app']);original=json.loads((base/'original-manifest.json').read_bytes());checked(old,original['files'])
 if original['material_sha256']!='7d8ae05dab162ec5eaded17a7ed779c14d092880553dcd96345cf3d3198e6cf0':raise ValueError('ORIGINAL_MATERIAL_PIN')
 sys.path.insert(0,str(old))
 from research_lab import pump4_closed_bar_intake_v1 as intake
 from research_lab import att1_lifecycle_journal as journal
 if pathlib.Path(intake.__file__).resolve()!=old/'research_lab/pump4_closed_bar_intake_v1.py' or pathlib.Path(journal.__file__).resolve()!=old/'research_lab/att1_lifecycle_journal.py':raise ValueError('ORIGINAL_IMPORT_IDENTITY')
 if intake.LifecycleJournal is not journal.LifecycleJournal:raise ValueError('PREEXISTING_JOURNAL_OVERLAY')
 name='research_lab.pump4_strict_read_journal_v1';spec=importlib.util.spec_from_file_location(name,folder/'pump4_strict_read_journal_v1.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 cls=module.Pump4StrictReadJournal
 if cls._append is not journal.LifecycleJournal._append or cls._locked is not journal.LifecycleJournal._locked:raise ValueError('WRITER_SEMANTICS_CHANGED')
 intake.LifecycleJournal=cls
 print(json.dumps(dict(schema='PUMP4_STRICT_READ_SELECTED_V1',manifest_sha256=pin,base_patch_sha256=m['base_patch_sha256'],parser_sha256=m['files']['pump4_strict_read_journal_v1.py'],only_data_intake_binding=True,full_chain_each_read=True,orders_allowed=False,financial_authority=False)),flush=True)
 script=base/'bootstrap.py';sys.argv=[str(script),'--patch-manifest-sha256',m['base_patch_sha256'],*remaining];runpy.run_path(str(script),run_name='__main__')

if __name__=='__main__':
 parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--strict-manifest-sha256',required=True);args,remaining=parser.parse_known_args();run(pathlib.Path(__file__).resolve().parent,args.strict_manifest_sha256,remaining)
