"""Versioned no-position/no-GO correction; retain original installed epoch."""
import base64,json,os,subprocess,sys,time
from pathlib import Path
b=json.loads(base64.b64decode(PACKAGE_B64));root=Path(b['root']);rt=root/'runtime';app=Path(b['app'])
sys.path.insert(0,str(root/'app-v1-1'))
from research_lab.kity_micro_handoff_v1 import config_from,verify_files,fresh_flat
from research_lab.kity_micro_physical_owner_v1 import sha,publish,load_bound_credentials,unit_state
from research_lab.kity_micro_transport_v1 import BybitReadTransport
old=config_from(str(rt/'config-v1-1.json'),'6d343d306e00ba1d0fc23a60c428a48c52496c3f70a8a33cfb39f9e3e914c51a');verify_files(old)
if any((rt/p).exists() for p in ('active-plan.json','owner-go.json','lifecycle.sqlite')) or list((rt/'wire').glob('send-*.json')):
 raise RuntimeError('NO_UPGRADE_WHILE_ANY_MONEY_STATE')
if any(not (rt/'results'/p.name).exists() for p in (rt/'commands').glob('*.json')):raise RuntimeError('UNPROCESSED_CONTROL_COMMAND')
unit=Path('/etc/systemd/system')/old['unit'];old_unit=unit.read_bytes()
if sha(old_unit)!='b100b5eeb8741e482050330bb790e06dd795c6e4e43fc4ad6467b795618b5f5b':raise RuntimeError('UNIT_CAS')
k,s=load_bound_credentials(old);reader=BybitReadTransport(k,s);before=fresh_flat(reader,'v12-before',rt)
app.mkdir(mode=0o700)
for rel,encoded in b['files'].items():
 p=app/rel;p.parent.mkdir(parents=True,exist_ok=True);data=base64.b64decode(encoded)
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
config=base64.b64decode(b['config']);new_unit=base64.b64decode(b['unit'])
if sha(config)!=b['config_sha256'] or sha(new_unit)!=b['unit_sha256']:raise RuntimeError('NEW_PIN_CONFLICT')
fd=os.open(b['config_path'],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(config);f.flush();os.fsync(f.fileno())
backup=rt/'unit-before-v1-2.service'
fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(old_unit);f.flush();os.fsync(f.fileno())
subprocess.run(['/root/by-bot/.venv/bin/python','-B','-m','research_lab.kity_micro_supervisor_v1','--help'],cwd=app,check=True,capture_output=True)
subprocess.run(['systemctl','stop',old['unit']],check=True,capture_output=True,timeout=10)
try:
 fresh_flat(reader,'v12-after-stop',rt)
 temp=unit.with_suffix('.service.kity-v12-tmp');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
 with os.fdopen(fd,'wb') as f:f.write(new_unit);f.flush();os.fsync(f.fileno())
 os.replace(temp,unit)
 subprocess.run(['systemctl','daemon-reload'],check=True,capture_output=True)
 subprocess.run(['systemctl','start',old['unit']],check=True,capture_output=True,timeout=10)
 out=dict(status='VERSIONED_ORDERS_OFF_UPGRADE_V1_2_APPLIED',at_ms=time.time_ns()//1000000,
     config_sha256=b['config_sha256'],unit_sha256=b['unit_sha256'],old_app_retained=True,old_config_retained=True,
     original_unit_backup_sha256=sha(backup.read_bytes()),new_owner=unit_state(old['unit']),flat_before=before,broker_writes=0)
 publish(rt/'upgrade-v1-2-receipt.json',out);print(json.dumps(out))
except Exception:
 subprocess.run(['systemctl','stop',old['unit']],check=True,capture_output=True)
 unit.write_bytes(old_unit);subprocess.run(['systemctl','daemon-reload'],check=True,capture_output=True)
 subprocess.run(['systemctl','start',old['unit']],check=True,capture_output=True)
 raise
