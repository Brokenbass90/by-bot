#!/usr/bin/env python3
"""Local, commands-only ATT1 archive. Acceptance declarations are not authentication.

Numeric proposal and raw evidence remain private. The caller must independently
verify provenance and target receipts. This builder neither connects nor deploys.
"""
from __future__ import annotations
import argparse,ast,hashlib,io,json,os,subprocess,tarfile,time
from pathlib import Path
from bot.att1_canary_preparation import _revalidate, MAX_EVIDENCE_AGE_MS
from scripts.package_att1_lifecycle import SOURCES as PUBLIC_SOURCES

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (*PUBLIC_SOURCES,'bot/att1_coordinator_adapter.py','bot/att1_canary_preparation.py')
CHECKS = {'local_targeted','target_python','historical_receipts','critical_review'}
AUTHORITY = {'money_authority':False,'orders_allowed':False,'promotion_authority':False}


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def sha(data):return hashlib.sha256(data).hexdigest()


def validate_closure(files):
    """Include local imports at any depth, including authenticated GET recovery."""
    for relative,raw in files.items():
        if not relative.endswith('.py'):continue
        for node in ast.walk(ast.parse(raw,filename=relative)):
            names=[]
            if isinstance(node,ast.Import):names=[x.name for x in node.names]
            elif isinstance(node,ast.ImportFrom):
                module=node.module or ''
                if node.level:
                    parents=relative.split('/')[:-node.level]
                    module='.'.join([*parents,module]).rstrip('.')
                names=[module]
                # from bot import X also has a concrete local submodule.
                names.extend(module+'.'+x.name for x in node.names)
            for name in names:
                if name.split('.')[0] not in {'bot','research_lab','scripts','strategies'}:continue
                path=name.replace('.','/')+'.py'
                if (ROOT/path).is_file() and path not in files:
                    raise ValueError('missing import dependency: '+path)


def build(out: Path, *, binding_path: Path, acceptance_path: Path) -> dict:
    v=_revalidate(json.loads(binding_path.read_bytes()))
    if 'handoff_binding' not in v or 'command_binding' in v:
        raise ValueError('complete private proposal/handoff, without a signal, required')
    a=json.loads(acceptance_path.read_bytes())
    fields={'schema_id','evidence_kind','source_tree_head','observed_ms','source_hashes','monolith_sha256',
            'checks','target_receipt_sha256','critical_review_receipt_sha256','provenance_receipt_sha256','owner_go','orders_allowed'}
    if (set(a)!=fields or a['schema_id']!='att1_canary_package_acceptance_v1'
            or a['evidence_kind'] not in {'SYNTHETIC_TEST_FIXTURE','AUTHENTICATED_OWNER_PROPOSAL'}
            or a['owner_go'] is not False or a['orders_allowed'] is not False
            or not isinstance(a['checks'],dict) or set(a['checks'])!=CHECKS
            or any(x!='PASS' for x in a['checks'].values())
            or type(a['observed_ms']) is not int or not 0<=v['now_ms']-a['observed_ms']<=MAX_EVIDENCE_AGE_MS):
        raise ValueError('incomplete/stale orders-OFF acceptance')
    for field in ('monolith_sha256','target_receipt_sha256','critical_review_receipt_sha256','provenance_receipt_sha256'):
        x=a[field]
        if not isinstance(x,str) or len(x)!=64 or any(c not in '0123456789abcdef' for c in x):
            raise ValueError('missing acceptance receipt hash')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if a['source_tree_head']!=head:raise ValueError('source HEAD mismatch')
    sources={p:(ROOT/p).read_bytes() for p in SOURCES}
    if {p:sha(raw) for p,raw in sources.items()}!=a['source_hashes']:
        raise ValueError('source hash mismatch')
    validate_closure(sources)
    monolith=(ROOT/'smart_pump_reversal_bot.py').read_bytes()
    if sha(monolith)!=a['monolith_sha256']:raise ValueError('monolith seam source mismatch')
    tree=ast.parse(monolith)
    seams=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_att1_prepare_new_canary']
    if len(seams)!=1:raise ValueError('missing inert monolith seam')
    seam='ATT1_CANARY_PREPARATION_ENABLE = False\n\n'+ast.unparse(seams[0])+'\n'
    # Exclude the runnable OLD money bot. Enabling this extracted function only
    # prepares commands; there is no financial runner, credentials or service.
    files={'app/'+p:raw for p,raw in sources.items()}
    files['app/bot/att1_canary_monolith_seam.py']=seam.encode()
    files['app/tests/fixtures/att1_lifecycle/att1_end_to_end_v1.json']=(ROOT/'tests/fixtures/att1_lifecycle/att1_end_to_end_v1.json').read_bytes()
    files['app/configs/research/att1_lifecycle_public_v1.json']=(ROOT/'configs/research/att1_lifecycle_public_v1.json').read_bytes()
    private_raw=canonical(v)+b'\n'
    rows=[{'path':p,'bytes':len(raw),'sha256':sha(raw)} for p,raw in sorted(files.items())]
    closure=sha(canonical(rows))
    if a['evidence_kind']=='AUTHENTICATED_OWNER_PROPOSAL':
        if not 0<=time.time_ns()//1_000_000-v['now_ms']<=MAX_EVIDENCE_AGE_MS:
            raise ValueError('fresh actual risk comparison required')
        # Frozen source acceptance cannot be attached to different uncommitted code.
        for relative,raw in sources.items():
            committed=subprocess.check_output(['git','show',head+':'+relative],cwd=ROOT)
            if committed!=raw:raise ValueError('uncommitted accepted source')
    readiness='ENGINEERING_FIXTURE_ONLY' if a['evidence_kind']=='SYNTHETIC_TEST_FIXTURE' else 'BUILD_READY_ORDERS_OFF'
    manifest={'schema_id':'att1_canary_orders_off_release_v1','source_tree_head':head,
              'monolith_sha256':a['monolith_sha256'],'closure_sha256':closure,'files':rows,
              'private_binding_sha256':sha(private_raw),'limits':'REDACTED_PRIVATE_NUMERIC_PROPOSAL',
              'acceptance_sha256':sha(canonical(a)),'evidence_kind':a['evidence_kind'],
              'readiness':readiness,'authority':AUTHORITY,'installed_on_money_service':False}
    files['release_manifest.json']=canonical(manifest)+b'\n'
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for relative,raw in sorted(files.items()):
            info=tarfile.TarInfo(relative);info.size=len(raw);info.mode=0o644
            info.uid=info.gid=info.mtime=0;archive.addfile(info,io.BytesIO(raw))
    raw=buffer.getvalue();out=out.resolve();out.mkdir(parents=True,exist_ok=True)
    private=out/'private_numeric_proposal.json'
    # Never follow a symlink or overwrite a different private binding.
    if private.exists() or private.is_symlink():
        if private.is_symlink() or private.read_bytes()!=private_raw:raise ValueError('private binding collision')
        private.chmod(0o600)
    else:
        fd=os.open(private,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as f:f.write(private_raw);f.flush();os.fsync(f.fileno())
    archive=out/('att1-canary-orders-off-'+closure[:16]+'.tar')
    if archive.exists() and (archive.is_symlink() or archive.read_bytes()!=raw):raise ValueError('archive collision')
    archive.write_bytes(raw)
    receipt={'archive':str(archive),'archive_sha256':sha(raw),'closure_sha256':closure,
             'private_binding':str(private),'private_binding_sha256':sha(private_raw),'files':len(rows),
             'source_tree_head':head,'readiness':readiness,'orders_allowed':False,'owner_go':False,
             'money_gate_met':False,'installed_on_money_service':False}
    (out/'package_receipt.json').write_bytes(canonical(receipt)+b'\n')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--binding',type=Path,required=True)
    parser.add_argument('--acceptance',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.out,binding_path=args.binding,acceptance_path=args.acceptance),sort_keys=True))
