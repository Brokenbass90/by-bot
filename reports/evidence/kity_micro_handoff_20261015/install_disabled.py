"""Run via SSH stdin with PACKAGE_B64 set to the local approved bundle.

No service activation, old owner mutation or broker operation. Create-exclusive
source epoch; subsequent handoff is a separate explicit operator action.
"""
import base64,json,os,subprocess,hashlib
from pathlib import Path
b=json.loads(base64.b64decode(PACKAGE_B64));root=Path(b['root']);app=root/'app';runtime=root/'runtime'
if root.exists():raise RuntimeError('SOURCE_EPOCH_EXISTS_NO_OVERWRITE')
root.mkdir(mode=0o700);app.mkdir(mode=0o700);runtime.mkdir(mode=0o700)
for rel,encoded in b['files'].items():
 if Path(rel).is_absolute() or '..' in Path(rel).parts:raise RuntimeError('PACKAGE_PATH')
 p=app/rel;p.parent.mkdir(parents=True,exist_ok=True)
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444)
 with os.fdopen(fd,'wb') as f:f.write(base64.b64decode(encoded));f.flush();os.fsync(f.fileno())
for p,encoded,pin,mode in ((runtime/'config.json',b['config'],b['config_sha256'],0o600),
 (Path('/etc/systemd/system/kity-execution-micro-owner.service'),b['unit'],b['unit_sha256'],0o644)):
 raw=base64.b64decode(encoded)
 if hashlib.sha256(raw).hexdigest()!=pin:raise RuntimeError('PIN_CONFLICT')
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
subprocess.run(['systemd-analyze','verify','/etc/systemd/system/kity-execution-micro-owner.service'],check=True,capture_output=True)
subprocess.run(['systemctl','daemon-reload'],check=True,capture_output=True)
print(json.dumps(dict(status='DISABLED_PACKAGE_INSTALLED',source_files=len(b['files']),config_sha256=b['config_sha256'],unit_sha256=b['unit_sha256'],broker_writes=0)))
