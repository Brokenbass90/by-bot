from pathlib import Path
import json,importlib.util,hashlib,time,sys,subprocess
F=Path('/opt/bybot-research/pump4-server-orders-off-20261023/tiny-activation-20261028-v1');PIN='66a7be9cbb134524ee43785e46c79920b05a06a1429a9eeb47e69c25eb8e6340'
s=importlib.util.spec_from_file_location('reviewed_activation',F/'activation.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a);p,b=a.load_packet(F,PIN);a.static_guards(p,b);a.off_not_sent(b)
root=Path(p['live_root']);assert not root.exists() and not (F/'activation-claim.json').exists() and not (F/'runner.json').exists() and not (F/'scope.json').exists()
assert a.UNIT.read_text()==b['units'][a.UNIT.name] and Path(p['wrapper_path']).read_text()==b['wrapper']['text']
G=a.build_generated(b,p,time.time_ns()//1000000);scratch=F/'unselected-rehearsal';scratch.mkdir(mode=0o700);unit=scratch/'pump4-execution-owner.service';unit.write_text(G['unit']);v=subprocess.run(['systemd-analyze','verify',str(unit)],capture_output=True,text=True,timeout=20);assert v.returncode==0,v.stderr
sys.path.insert(0,p['financial_app']);sp=importlib.util.spec_from_file_location('unselected_health',F/'health.py');h=importlib.util.module_from_spec(sp);sp.loader.exec_module(h);proof=h.collect_live(G['config'],G['scope'])
assert proof['status']=='LIVE_FLAT_WAITING_SIGNAL' and not root.exists() and not (F/'activation-claim.json').exists() and not (F/'runner.json').exists()
assert a.UNIT.read_text()==b['units'][a.UNIT.name] and Path(p['wrapper_path']).read_text()==b['wrapper']['text']
print(json.dumps(dict(schema='PUMP4_EXACT_UNSELECTED_ACTIVATION_REHEARSAL_V1',status='PASS',packet_sha256=PIN,observed_ms=time.time_ns()//1000000,policy=p['policy'],unit_template_verified=True,would_be_live_health=proof,actual_financial_mode='ORDERS_OFF',live_root_created=False,go_created=False,financial_units_changed=0,financial_owner_constructed=False,lease_claimed=False,broker_writes=0)))
