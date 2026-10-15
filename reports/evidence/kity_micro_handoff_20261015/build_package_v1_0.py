"""Build explicit nonsecret source closure and inert systemd package."""
import base64,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
E=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
raw=lambda x:(json.dumps(x,sort_keys=True,indent=2)+'\n').encode()
files=['bot/__init__.py','bot/kity_m3_orders_off.py',
 'research_lab/kity_execution_micro_v1.py','research_lab/kity_execution_micro_runtime_v1.py',
 'research_lab/kity_execution_micro_bybit_v1.py','research_lab/kity_micro_transport_v1.py',
 'research_lab/kity_micro_account_bridge_v1.py','research_lab/kity_micro_preflight_v1.py',
 'research_lab/kity_micro_physical_owner_v1.py','research_lab/kity_micro_supervisor_v1.py',
 'research_lab/kity_micro_handoff_v1.py',
 'reports/evidence/kity_micro_live_20261015/build_readonly_dossier.py',
 'reports/evidence/kity_bybit_c2_actual_20261015/c2_public_receipt.json',
 'configs/research/kity_execution_micro_owner_bounds_v3_20261015.json']
root='/opt/bybot-research/kity-micro-owner-20261015';app=root+'/app';runtime=root+'/runtime'
unit='kity-execution-micro-owner.service'
template=f'''[Unit]
Description=Exclusive KITY execution micro owner (default orders OFF)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=root
WorkingDirectory={app}
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUNBUFFERED=1
ExecStart=/root/by-bot/.venv/bin/python -B -m research_lab.kity_micro_supervisor_v1 --config {runtime}/config.json --config-sha256 <PIN>
Restart=always
RestartSec=2
WatchdogSec=45
NotifyAccess=main
KillMode=control-group
KillSignal=SIGKILL
TimeoutStopSec=5
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths={runtime}
PrivateTmp=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

[Install]
WantedBy=multi-user.target
'''
inventory=json.loads((ROOT/'.private/kity_micro_handoff_20261015/inventory.json').read_bytes())
cron_sources=json.loads((ROOT/'.private/kity_micro_handoff_20261015/cron_sources.json').read_bytes())
restarts=json.loads((ROOT/'.private/kity_micro_handoff_20261015/restart_sources.json').read_bytes())
inhibitor=f'[Unit]\nConditionPathExists=!{runtime}/HANDOFF_ACTIVE\n\n[Service]\nRestart=no\nKillSignal=SIGKILL\n'
originals={u:inventory['units'][u] for u in ('bybot.service','trading-journal-web.service')}
guards={'/etc/systemd/system/'+u:v['fragment_sha256'] for u,v in inventory['units'].items()}
guards.update({'/root/by-bot/'+p:v['sha256'] for p,v in cron_sources.items()})
guards.update({'/root/by-bot/'+p:v['sha256'] for p,v in restarts.items() if isinstance(v,dict) and 'sha256' in v})
guards.update({'/root/by-bot/smart_pump_reversal_bot.py':'c8ca2c325884a31521f160e9d690c301b8a58297443f32f3cde395e9c9a699d1',
 '/root/by-bot/web/main.py':'96c8a2bc6beffce685eb8d31e8fc771c72cd81e0860accf0ab5d32239c845e34'})
config=dict(schema='kity_micro_physical_owner_config_v1',app_root=app,runtime_root=runtime,unit=unit,
 source_files={p:sha((ROOT/p).read_bytes()) for p in files},guard_source_files=guards,
 credential_source='/root/by-bot/.env',credential_source_sha256=inventory['env_source_sha256'],
 account_fingerprint=inventory['account_fingerprint'],original_cron_sha256=inventory['cron_sha256'],
 original_units=originals,inhibit_marker=runtime+'/HANDOFF_ACTIVE',inhibitor_text=inhibitor,
 inhibitors={u:sha(inhibitor.encode()) for u in originals},unit_template_sha256=sha(template.encode()),
 bounds_file='configs/research/kity_execution_micro_owner_bounds_v3_20261015.json',money_go=False,
 purpose='EXECUTION_MICRO_LIVE',default_orders_off=True,owner_scope='GO KITY SCOPED HANDOFF IMPLEMENTATION — ORDERS OFF')
config_bytes=raw(config);cp=sha(config_bytes);unit_bytes=template.replace('<PIN>',cp).encode()
bundle=dict(root=root,files={p:base64.b64encode((ROOT/p).read_bytes()).decode() for p in files},
 config=base64.b64encode(config_bytes).decode(),unit=base64.b64encode(unit_bytes).decode(),
 config_sha256=cp,unit_sha256=sha(unit_bytes))
manifest=dict(schema='kity_micro_physical_package_manifest_v1',app_root=app,runtime_root=runtime,
 source_files=config['source_files'],source_count=len(files),config_sha256=cp,unit_sha256=sha(unit_bytes),
 unit=unit,broker_writes=0,orders_off=True,monetary_go=False)
for p,data in ((E/'package_manifest.json',raw(manifest)),(E/'owner_unit.service',unit_bytes),
              (ROOT/'.private/kity_micro_handoff_20261015/package_bundle.json',raw(bundle))):
 p.write_bytes(data)
print(json.dumps(manifest))
