"""One exact DATA-only correction after catalogue failure; no financial actions."""
import datetime,hashlib,json,os,runpy,subprocess,time,uuid
from pathlib import Path
BASE=Path('/opt/bybot-research/polymarket-ws-data-20261102')
OLD=BASE/'candidate-ca49093d3ca56ed4';NEW=BASE/'candidate-b79fcd827bea31cc'
OLD_PIN='feea58d8b4d624a651e837f6258a6b4943707324297111e52d2a2c916d3e5b74'
NEW_PIN='c51b3c6dfbc1530bd1f498dcb14d11866b121ae4cec0d90ab8f90e78c5153644'
INSTALL_PIN='7119b90566dc633cfd706851a8a82ccd31ab7368a42ac769d5d7701a6f8149c4'
def sha(b):return hashlib.sha256(b).hexdigest()
def check(ok,message):
    if not ok:raise ValueError(message)
def main():
    installer=NEW/'app/reports/evidence/polymarket_ws_data_20261102/install-data-only.py'
    check(sha(installer.read_bytes())==INSTALL_PIN,'INSTALLER_DRIFT')
    f=runpy.run_path(str(installer));_,old=f['load'](OLD/'data-packet.json',OLD_PIN);_,new=f['load'](NEW/'data-packet.json',NEW_PIN)
    before=f['snapshot'](new);check(not (OLD/'activation-claim.json').exists(),'OLD_WS_ACTIVATION_EXISTS')
    t=datetime.datetime.now(datetime.timezone.utc);check(not(t.date()==datetime.date(2026,11,2) and 14*60+10<=t.hour*60+t.minute<14*60+50),'MONTHLY_QUIET_WINDOW')
    mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))
    check(mem>=512*1024,'MEMORY_PREFLIGHT')
    import shutil
    check(shutil.disk_usage(BASE).free>=3*2**30,'DISK_PREFLIGHT')
    for role in ('sports','clob'):
        s=f['state']('poly-ws-data-'+role+'.service');check(s['MainPID']=='0' and s['NRestarts']=='0' and s['ActiveState']=='inactive','OLD_WS_NOT_INACTIVE')
    check(f['state']('poly-ws-data-catalog.service')['ActiveState']=='inactive','CATALOG_NOT_STOPPED')
    for name,pin in old['units'].items():check(sha(f['read'](Path('/etc/systemd/system')/name))==pin,'OLD_DATA_UNIT_DRIFT')
    f['once'](NEW/'replacement-claim.json',dict(observed_ms=f['now'](),before=before,old_packet=OLD_PIN,new_packet=NEW_PIN,no_blind_retry=True))
    for name in sorted(new['units']):
        if new['units'][name]==old['units'][name]:continue
        path=Path('/etc/systemd/system')/name;tmp=path.with_name(name+'.poly-data-'+uuid.uuid4().hex)
        fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o644)
        with os.fdopen(fd,'wb') as stream:stream.write(f['read'](NEW/'units'/name));stream.flush();os.fsync(stream.fileno())
        check(sha(f['read'](path))==old['units'][name],'DATA_UNIT_CHANGED');os.replace(tmp,path)
    fd=os.open('/etc/systemd/system',os.O_RDONLY);os.fsync(fd);os.close(fd)
    f['command']('systemctl','daemon-reload');f['command']('systemctl','start','poly-ws-data-catalog.service');f['command']('systemctl','enable','--now','poly-ws-data-catalog.timer')
    after=f['snapshot'](new);result=dict(status='DATA_CATALOG_REPLACEMENT_ACCEPTED',observed_ms=f['now'](),before=before,after=after,financial_commands=0,ws_not_started=True)
    f['once'](NEW/'replacement-receipt.json',result);print(json.dumps(result))
if __name__=='__main__':main()
