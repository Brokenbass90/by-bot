"""Build a review candidate from existing NONSECRET configuration/code inputs.

No API requests, key discovery, active file changes, owner GO or runtime creation.
Credential input, if supplied, contains only a path and two SHA256 values.
"""
import argparse,copy,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from scripts import pump4_source_handoff_v1 as H

def assemble(inputs,output,remote_dir,*,namespace_base=None,new_binding=None):
    output=Path(output);remote=Path(remote_dir);base=Path(namespace_base or H.BASE)
    H.need(remote.is_relative_to(base),'PACKET_NAMESPACE')
    oldc=inputs['config'];olds=inputs['scope'];c=copy.deepcopy(oldc);s=copy.deepcopy(olds)
    candidate=base/'candidate-05f89618d8550664';root=str(candidate/'runtime/tiny-source-repair-next-20261101')
    health=inputs['health_source'].replace("CONFIG=Path('/PACKET/runner.json')","CONFIG=Path('"+str(remote/'runner.json')+"')")
    H.need(H.sha(inputs['health_source'].encode())==H.HEALTH_TEMPLATE_PIN,'HEALTH_TEMPLATE')
    notification=dict(inputs['notifications'],output_root=root+'/notifications')
    payload={'handoff.py':inputs['installer_source'].encode(),'base_ops.py':inputs['base_ops_source'].encode(),
        'health.py':health.encode(),'health-legacy-immutable.py':inputs['legacy_health_source'].encode(),
        'old-owner.service':inputs['old_unit'].encode(),'old-wrapper.py':inputs['old_wrapper'].encode(),
        'old-original-owner.json':H.encode(inputs['original']),
        'old-notifications.json':H.encode(inputs['notifications']),
        'before.json':H.encode({k:inputs[k] for k in ('config','scope','original','notifications')}),
        'notifications.json':H.encode(notification)}
    H.need(H.sha(payload['old-original-owner.json'])==oldc['original_owner']['sha256'],'LEGACY_CONFIG_PIN')
    H.need(H.sha(payload['old-notifications.json'])==oldc['notifications']['sha256'],'OLD_NOTIFICATION_PIN')
    c.update(candidate_source='CURRENT_H1_PUBLICATIONS_V1',app_root=str(candidate/'app'),custody_runtime_root=root)
    c['source_files']={k:inputs['source_manifest'][k] for k in oldc['source_files']}
    c['execution_policy']['source_manifest_sha256']=H.digest(c['source_files'])
    c['notifications']=dict(path=str(remote/'notifications.json'),sha256=H.sha(payload['notifications.json']))
    if new_binding is not None:
        keys={'credential_source','credential_source_sha256','account_fingerprint'}
        H.need(set(new_binding)==keys and new_binding['credential_source']!=oldc['credential_source'],'SEPARATE_METADATA_ONLY_BINDING')
        H.need(all(re.fullmatch('[0-9a-f]{64}',new_binding[k]) for k in ('credential_source_sha256','account_fingerprint')),'BINDING_HASHES_ONLY')
        c.update(new_binding)
        original=dict(inputs['original'],**new_binding)
        payload['original-owner.json']=H.encode(original)
        c['original_owner']=dict(path=str(remote/'original-owner.json'),sha256=H.sha(payload['original-owner.json']))
        c['guard_source_files'][c['credential_source']]=c['credential_source_sha256']
    s.update(root=root,valid_from_ms=olds['valid_until_ms'],valid_until_ms=olds['valid_until_ms']+7*H.DAY,
        account_fingerprint=c['account_fingerprint'],execution_policy=copy.deepcopy(c['execution_policy']))
    wrapper=("from pathlib import Path\nimport hashlib,runpy\np=Path('"+str(remote/'health.py')+"')\nif hashlib.sha256(p.read_bytes()).hexdigest()!='"+H.sha(payload['health.py'])+"':raise RuntimeError('HEALTH_SOURCE_PIN')\nrunpy.run_path(str(p),run_name='__main__')\n").encode()
    payload['new-wrapper.py']=wrapper
    c['guard_source_files'][inputs['wrapper_path']]=H.sha(wrapper)
    for n in ('health.py','health-legacy-immutable.py','notifications.json'):c['guard_source_files'][str(remote/n)]=H.sha(payload[n])
    unit=inputs['old_unit'].replace(oldc['app_root'],c['app_root']).replace(str(H.OLD_CONFIG),str(remote/'runner.json')).replace(olds['root'],root)
    unit=unit.replace('Environment=PYTHONDONTWRITEBYTECODE=1\n','Environment=PYTHONDONTWRITEBYTECODE=1\nEnvironment=PYTHONOPTIMIZE=0\n')
    c['unit_template_sha256']=H.sha(re.sub(r'--config-sha256 [0-9a-f]{64}','--config-sha256 <PIN>',unit).encode())
    s['runner_config_sha256']=H.digest({k:v for k,v in c.items() if k!='authority'})
    c['authority']=dict(path=str(remote/'scope.json'),sha256=H.sha(H.encode(s)))
    unit=re.sub(r'--config-sha256 [0-9a-f]{64}','--config-sha256 '+H.sha(H.encode(c)),unit)
    payload.update({'runner.json':H.encode(c),'scope.json':H.encode(s),'new-owner.service':unit.encode()})
    meta=inputs['metadata']
    p=dict(schema='PUMP4_SOURCE_REPAIR_OWNER_PACKET_V1',packet_dir=str(remote),candidate_root=str(candidate),
        source_manifest_sha256=H.SOURCE_PIN,old_account_identity_sha256=H.OLD_UID_PIN,
        old_owner_pid=meta['old_owner_pid'],old_barrier_inode=meta['old_barrier_inode'],old_money_anchors=meta['old_money_anchors'],
        observer_lock=meta['observer_lock'],observer_lock_inode=meta['observer_lock_inode'],
        wrapper_path=inputs['wrapper_path'],preserved_units=H.PRESERVED_UNITS,
        files={n:H.sha(raw) for n,raw in payload.items()},
        terms=dict(allocation_usdt='50',max_gross_usdt='30',reserve_usdt='20',scenario_risk_usdt='1',
            max_entries=1,max_positions=1,cross_margin=True,isolated_allocation=False,guaranteed_loss_bound=False,
            valid_from_ms=s['valid_from_ms'],valid_until_ms=s['valid_until_ms'],required_key_until_ms=s['valid_until_ms']+8*H.DAY,
            no_automatic_extension=True,source_epoch_unchanged=True,rollback='REVOKE_ENTRIES_KEEP_CUSTODY_AFTER_START'))
    p['material_sha256']=H.digest(p)
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    for n,raw in payload.items():H.once(output/n,raw)
    H.once(output/'candidate.json',H.encode(p))
    return p

def seal(output,offline,review):
    output=Path(output);p=json.loads(H.read(output/'candidate.json'))
    H.need(offline['material_sha256']==review['material_sha256']==p['material_sha256'],'PROOF_MATERIAL')
    for n,value in (('offline-acceptance.json',offline),('independent-review.json',review)):
        raw=H.encode(value);H.once(output/n,raw);p['files'][n]=H.sha(raw)
    H.once(output/'packet.json',H.encode(p));return H.sha(H.encode(p))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--input',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--remote-directory',required=True)
    ap.add_argument('--new-binding',type=Path);a=ap.parse_args()
    value=assemble(json.loads(a.input.read_bytes()),a.output,a.remote_directory,
        new_binding=json.loads(a.new_binding.read_bytes()) if a.new_binding else None)
    print(json.dumps(dict(status='UNSEALED_REVIEW_CANDIDATE_NO_GO',material_sha256=value['material_sha256'],terms=value['terms'])))
if __name__=='__main__':main()
