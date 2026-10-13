"""One offline actual-fee-to-first-dossier transaction; always orders-OFF.

Reuse the existing posted-cost/lifecycle/physical-binding/intent/dossier rules.
No broker client, polling, installer, reservation, permit or activation path.
The caller supplies one actual terminal capture and a fresh LIVE preparation.
"""
import hashlib
from pathlib import Path
from decimal import Decimal, ROUND_DOWN

from research_lab.alpaca_dynamic_v1 import canonical, digest
from research_lab.alpaca_dynamic_live_runtime_v1 import read_json, safe_path
from research_lab.alpaca_dynamic_first_intent_v1 import prepare_first_intent
from research_lab import alpaca_live_readiness_v1 as readiness
from research_lab.alpaca_orders_off_handoff_v2 import bind_final_paper

ROLES={'cash_before','initial','rearm','protocol','arm','initial_evidence',
       'deployment','binding_template','policy','fixed_intent'}


def pin(path):
    p=safe_path(str(Path(path).absolute()),exists=True)
    return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def check_rows(rows):
    for row in rows:
        if pin(row['path'])!=row:raise ValueError('CLOSURE_STATIC_SOURCE_DRIFT')


def unused_output(value):
    p=Path(value)
    if p.exists() and not p.is_symlink():raise ValueError('CLOSURE_ATTEMPT_ALREADY_EXISTS')
    return safe_path(value)


def code_pins():
    from research_lab import alpaca_dynamic_first_intent_v1,alpaca_orders_off_handoff_v2
    return [pin(p) for p in (Path(__file__),Path(readiness.__file__),
        Path(alpaca_dynamic_first_intent_v1.__file__),Path(alpaca_orders_off_handoff_v2.__file__))]


def freeze_manifest(inputs,*,output_dir):
    if set(inputs)!=ROLES:raise ValueError('CLOSURE_EXACT_STATIC_ROLES_REQUIRED')
    out=unused_output(str(Path(output_dir).absolute()))
    row=dict(schema='ALPACA_FEE_TO_LIVE_CLOSURE_MANIFEST_V1',
        inputs={n:pin(p) for n,p in sorted(inputs.items())},code_files=code_pins(),
        output_dir=str(out),orders_allowed=False,live_orders_allowed=False,
        automatic_retry=False,polling=False)
    return {**row,'manifest_sha256':digest(row)}


def close_once(manifest,*,terminal_capture,live_preparation,now_ms):
    if manifest.get('manifest_sha256')!=digest({k:v for k,v in manifest.items() if k!='manifest_sha256'}):
        raise ValueError('CLOSURE_MANIFEST_PIN_CONFLICT')
    if (manifest.get('schema')!='ALPACA_FEE_TO_LIVE_CLOSURE_MANIFEST_V1'
        or set(manifest['inputs'])!=ROLES or manifest['orders_allowed'] is not False
        or manifest['live_orders_allowed'] is not False or manifest['polling'] is not False
        or manifest['automatic_retry'] is not False):raise ValueError('CLOSURE_SCOPE_CONFLICT')
    out=unused_output(manifest['output_dir'])
    out.mkdir(mode=0o700)
    try:
        check_rows(manifest['code_files']);check_rows(manifest['inputs'].values())
        paths={n:row['path'] for n,row in manifest['inputs'].items()}
        terminal=read_json(str(terminal_capture))
        fee=readiness.derive_paper_posted_cost_closure_v2(
            cash_before_path=paths['cash_before'],initial_path=paths['initial'],
            rearm_path=paths['rearm'],terminal_path=str(terminal_capture),
            protocol_path=paths['protocol'],now_ms=now_ms)
        paper=readiness.verify_paper_lifecycle(read_json(paths['arm']),read_json(paths['initial_evidence']),
            read_json(paths['rearm'])['response'],terminal['response'],fee,now_ms=now_ms)
        if paper['status']!='PAPER_EXECUTION_PASS':result=paper
        else:
            deployment=bind_final_paper(read_json(paths['deployment']),paper,now_ms=now_ms)
            readiness.write_new(out/'cost-closure.json',canonical(fee))
            readiness.write_new(out/'paper.json',canonical(paper))
            readiness.write_new(out/'deployment-bound.json',canonical(deployment))
            binding=read_json(paths['binding_template'])
            # A new separate attestation; never edit the original install receipt.
            binding['sources']['paper']=pin(out/'paper.json')
            readiness.write_new(out/'binding.json',canonical(binding))
            preparation=read_json(str(live_preparation));snapshot=preparation['snapshot']
            fixed=read_json(paths['fixed_intent']);policy=read_json(paths['policy'])
            price_pin=next(row['sha256'] for row in preparation['source_files']
                if read_json(row['path'])==snapshot or read_json(row['path']).get('snapshot')==snapshot)
            # Price and time are the fresh original-source fields, not an old preview.
            intent=prepare_first_intent(policy=policy,binding=binding,**fixed,
                max_limit_price=str(Decimal(str(snapshot['quote']['ap'])).quantize(Decimal('.01'),rounding=ROUND_DOWN)),
                price_source_sha256=price_pin,
                quote_cts_ms=readiness._ms(snapshot['quote']['t']),prepared_ms=snapshot['observed_ms'])
            result=readiness.pre_entry_dossier(paper=paper,deployment=deployment,binding=binding,
                intent=intent,policy=policy,preparation=preparation,now_ms=now_ms)
            if result['status']=='READY_FOR_LIVE_GO':readiness.write_new(out/'first-intent.json',canonical(intent))
    except (ValueError,KeyError,TypeError,OSError,StopIteration,ArithmeticError) as exc:
        result=readiness.blocked(str(exc) or type(exc).__name__)
    readiness.write_new(out/'terminal.json',canonical(result))
    return result
