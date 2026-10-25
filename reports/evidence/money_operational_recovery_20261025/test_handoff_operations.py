"""Offline physical handoff tests: fake systemd/provider, real temporary flock."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from research_lab.kity_micro_physical_owner_v1 import AccountLease
from research_lab import pump4_selected_runner_v1 as runner
from research_lab import pump4_runtime_sources_v1 as runtime_sources
from research_lab import pump4_bybit_sources_v1 as bybit
from research_lab import kity_micro_physical_owner_v1 as physical
from research_lab import pump4_account_adapter_v1 as adapter
from research_lab.alpaca_dynamic_v1 import digest

spec=importlib.util.spec_from_file_location('handoff_operations',Path(__file__).with_name('handoff-operations.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
sha=lambda raw:hashlib.sha256(raw).hexdigest()

class Fixture:
    def __init__(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.systemd=self.root/'systemd';self.systemd.mkdir()
        self.oldroot=self.root/'old';self.oldroot.mkdir()
        self.newroot=self.root/'new';self.newroot.mkdir()
        self.lock=self.oldroot/'account.lock';self.lease=AccountLease(self.lock);self.inode=self.lease.inode
        self.old=dict(unit='kity-execution-micro-owner.service',custody_runtime_root=str(self.oldroot),runtime_root=str(self.oldroot),account_lock_inode=self.inode,account_fingerprint='fixture-fingerprint')
        self.config=dict(unit='pump4-execution-owner.service',mode='ORDERS_OFF',source_files={},custody_runtime_root=str(self.newroot),inhibit_marker=str(self.root/'marker'),original_owner=self.pin('old.json',self.old))
        self.scope=dict(mode='ORDERS_OFF',root=str(self.newroot),runner_config_sha256=runner.config_sha(self.config))
        self.config['authority']=self.pin('scope.json',self.scope)
        self.configpin=self.pin('config.json',self.config)
        self.packet=dict(candidate=str(self.root),config=self.configpin,inhibitor_path=str(self.systemd/(self.old['unit']+'.d')/'90-kity-micro-inhibit.conf'),inhibitor_text='[Unit]\nConditionPathExists=!/fixture-marker\n',marker_text='reviewed handoff\n',unit_text='[Service]\nType=simple\nRestart=no\n')
        self.packet.update(inhibitor_sha256=sha(self.packet['inhibitor_text'].encode()),unit_sha256=sha(self.packet['unit_text'].encode()))
        self.packetpin=self.pin('packet.json',self.packet)
        self.pin('acceptance.json',dict(status='PASS',counts=dict(failures=0,errors=0,skipped=0)))
        f=self.root/'app/tests/fixtures';f.mkdir(parents=True);(f/'pump4_cycle_20261022.json').write_text('{"expected_plan":{}}')
        self.fragment=self.systemd/self.config['unit'];self.drop=Path(self.packet['inhibitor_path']);self.marker=Path(self.config['inhibit_marker'])
        self.oldstate=self.unit(True,str(self.systemd/self.old['unit']))
        self.newstate=self.unit(False,'')
        self.oldstate['UnitFileState']='enabled'
        self.calls=[];self.gets=0;self.receipt=True;self.start_failure=False;self.old_start_failure=False
        self.refresh_heartbeat();self.stack=contextlib.ExitStack()
        patches=[patch.object(m,'SYSTEMD',self.systemd),patch.object(m,'guard_original',lambda c:self.lock),patch.object(m,'state',self.state),patch.object(m,'systemctl',self.systemctl),patch.object(m.subprocess,'run',return_value=SimpleNamespace(stdout=b'')),patch.object(runner,'source_pins',return_value={}),patch.object(runtime_sources,'TrustedSources',lambda *a:self),patch.object(physical,'load_bound_credentials',return_value=('fixture-key','fixture-secret')),patch.object(adapter,'frozen_plan',lambda p:None),patch.object(bybit,'flat_account',self.flat_view)]
        for p in patches:self.stack.enter_context(p)
        if hasattr(m,'lock_held_by'):self.stack.enter_context(patch.object(m,'lock_held_by',self.lock_held))
        if hasattr(m,'STARTUP_TIMEOUT_SECONDS'):self.stack.enter_context(patch.object(m,'STARTUP_TIMEOUT_SECONDS',0))
    def pin(self,name,data):
        p=self.root/name;p.write_text(json.dumps(data));return dict(path=str(p),sha256=sha(p.read_bytes()))
    def unit(self,active,fragment):
        return dict(ActiveState='active' if active else 'inactive',SubState='running' if active else 'dead',MainPID=str(os.getpid()) if active else '0',UnitFileState='disabled',FragmentPath=fragment,DropInPaths='',Job='',ExecStop='',ExecStopPost='',NRestarts='0',Restart='no')
    def state(self,unit):return dict(self.oldstate if unit==self.old['unit'] else self.newstate)
    def refresh_heartbeat(self):
        (self.oldroot/'heartbeat.json').write_text(json.dumps(dict(mode='ORDERS_OFF',phase='TERMINAL',state=dict(phase='TERMINAL'),pid=os.getpid(),at_ms=m.time.time_ns()//1000000,account_lock_inode=self.inode)))
    def flat(self,*a,**k):self.gets+=1;return {},{}
    def flat_view(self,*a,**k):return dict(source_ms=m.time.time_ns()//1000000,positions_flat=True,open_orders_empty=True,borrowed_funds='0',margin_mode='REGULAR_MARGIN',available_balance='100')
    def lock_held(self,lock,pid):
        if str(pid)!=str(os.getpid()):return False
        try:lease=AccountLease(lock)
        except BlockingIOError:return True
        lease.close();return False
    def systemctl(self,*args):
        self.calls.append(args)
        if args==('daemon-reload',):
            self.oldstate['DropInPaths']=str(self.drop) if self.drop.exists() else ''
            self.newstate['FragmentPath']=str(self.fragment) if self.fragment.exists() else ''
            return ''
        op,_,unit=args;isold=unit==self.old['unit'];target=self.oldstate if isold else self.newstate
        if op=='disable':
            if target['MainPID']!='0' and self.lease is not None:self.lease.close();self.lease=None
            target.update(ActiveState='inactive',SubState='dead',MainPID='0',UnitFileState='disabled')
        elif op=='enable':
            if (self.old_start_failure if isold else self.start_failure):
                target.update(ActiveState='failed',SubState='failed',MainPID='0',UnitFileState='enabled');return ''
            if self.lease is None:self.lease=AccountLease(self.lock)
            target.update(ActiveState='active',SubState='running',MainPID=str(os.getpid()),UnitFileState='enabled')
            if isold:self.refresh_heartbeat()
            elif self.receipt:
                d=self.newroot/'supervisor/receipts';d.mkdir(parents=True,exist_ok=True)
                (d/'fixture-1.json').write_text(json.dumps(dict(schema='PUMP4_EXECUTION_SUPERVISOR_RECEIPT_V1',pid=os.getpid(),run_id='fixture',tick=1,observed_ms=m.time.time_ns()//1000000,scope_sha256=digest(self.scope),runner_config_sha256=self.configpin['sha256'],mode='ORDERS_OFF',result=dict(status='NO_CANDIDATE'),broker_writes=0)))
        return ''
    def artifacts(self,drop=True,fragment=False):
        m.once_file(self.marker,self.packet['marker_text'].encode())
        if drop:m.once_file(self.drop,self.packet['inhibitor_text'].encode())
        if fragment:m.once_file(self.fragment,self.packet['unit_text'].encode())
        self.systemctl('daemon-reload');self.calls.clear()
    def stop_old(self):self.systemctl('disable','--now',self.old['unit']);self.calls.clear()
    def run(self,mode):
        with contextlib.redirect_stdout(io.StringIO()):return m.run(self.packetpin['path'],self.packetpin['sha256'],mode)
    def close(self):
        self.stack.close()
        if self.lease is not None:self.lease.close()
        self.temp.cleanup()

class HandoffTests(unittest.TestCase):
    def setUp(self):self.f=Fixture()
    def tearDown(self):self.f.close()
    def test_explicit_complete_stopped_after_signal9_starts_new_once(self):
        real=self.f.systemctl
        def control(*args):
            result=real(*args)
            if args==('disable','--now',self.f.old['unit']):
                self.f.oldstate.update(ActiveState='failed',SubState='failed',Result='signal',ExecMainStatus='9')
            return result
        with patch.object(m,'systemctl',control):
            with self.assertRaisesRegex(ValueError,'OLD_OWNER_STILL_ACTIVE'):self.f.run('handoff')
        self.assertFalse(self.f.fragment.exists())
        marker=self.f.marker.read_bytes();drop=self.f.drop.read_bytes()
        marker_inode=self.f.marker.stat().st_ino;drop_inode=self.f.drop.stat().st_ino
        result=self.f.run('complete-stopped')
        self.assertEqual(result['status'],'PUMP4_ORDERS_OFF_SELECTED')
        self.assertEqual(result['operation_mode'],'complete-stopped')
        self.assertEqual(self.f.calls.count(('disable','--now',self.f.old['unit'])),1)
        self.assertEqual(self.f.calls.count(('enable','--now',self.f.config['unit'])),1)
        self.assertEqual(self.f.marker.read_bytes(),marker);self.assertEqual(self.f.drop.read_bytes(),drop)
        self.assertEqual(self.f.marker.stat().st_ino,marker_inode);self.assertEqual(self.f.drop.stat().st_ino,drop_inode)
        self.assertEqual(self.f.lock.stat().st_ino,self.f.inode)
        self.assertFalse((self.f.newroot/'owner-go.json').exists())
        with self.assertRaises(ValueError):self.f.run('handoff')
        with self.assertRaises(ValueError):self.f.run('complete-stopped')
        self.assertEqual(self.f.calls.count(('enable','--now',self.f.config['unit'])),1)
    def test_complete_stopped_requires_exact_marker_and_inhibitor(self):
        for kind in ('missing_marker','missing_drop','unknown_marker','unknown_drop','unknown_override'):
            with self.subTest(kind=kind):
                f=Fixture()
                try:
                    f.artifacts();f.stop_old()
                    if kind=='missing_marker':f.marker.unlink()
                    elif kind=='missing_drop':f.drop.unlink()
                    elif kind=='unknown_marker':f.marker.write_text('unknown')
                    elif kind=='unknown_drop':f.drop.write_text('unknown')
                    else:(f.drop.parent/'91-unknown.conf').write_text('unknown')
                    with self.assertRaises(ValueError):f.run('complete-stopped')
                    self.assertEqual(f.calls,[]);self.assertFalse(f.fragment.exists())
                finally:f.close()
    def test_complete_stopped_rejects_previous_new_attempt_or_unproven_old_state(self):
        for kind in ('fragment','old_active','old_enabled','nonterminal','lock_held','GO'):
            with self.subTest(kind=kind):
                f=Fixture()
                try:
                    f.artifacts(fragment=kind=='fragment')
                    if kind!='old_active':f.stop_old()
                    if kind=='old_enabled':f.oldstate['UnitFileState']='enabled'
                    elif kind=='nonterminal':
                        p=f.oldroot/'heartbeat.json';row=json.loads(p.read_bytes());row['phase']='OPEN';p.write_text(json.dumps(row))
                    elif kind=='lock_held':f.lease=AccountLease(f.lock)
                    elif kind=='GO':(f.newroot/'owner-go.json').write_text('preserve existing GO')
                    with self.assertRaises((ValueError,BlockingIOError)):f.run('complete-stopped')
                    self.assertEqual(f.calls,[])
                    if kind=='GO':self.assertEqual((f.newroot/'owner-go.json').read_text(),'preserve existing GO')
                finally:f.close()
    def test_enable_success_without_receipt_is_not_selection(self):
        self.f.receipt=False
        with self.assertRaisesRegex(ValueError,'STARTUP'):self.f.run('handoff')
        self.assertEqual(list(self.f.root.glob('handoff-*.json')),[])
    def test_partial_marker_drop_old_still_active_can_rollback(self):
        self.f.artifacts();r=self.f.run('rollback')
        self.assertEqual(r['status'],'ORIGINAL_OWNER_RESTORED_ORDERS_OFF')
        self.assertFalse(self.f.drop.exists());self.assertTrue(self.f.marker.exists())
        self.assertNotIn(('disable','--now',self.f.old['unit']),self.f.calls)
    def test_crash_after_drop_unlink_before_old_restart_can_rollback(self):
        self.f.artifacts(drop=False);self.f.stop_old();r=self.f.run('rollback')
        self.assertEqual(r['status'],'ORIGINAL_OWNER_RESTORED_ORDERS_OFF')
        self.assertEqual(self.f.lock.stat().st_ino,self.f.inode)
    def test_failed_new_start_then_explicit_rollback_no_handoff_retry(self):
        self.f.start_failure=True
        with self.assertRaisesRegex(ValueError,'STARTUP'):self.f.run('handoff')
        self.f.run('rollback')
        self.assertEqual(self.f.calls.count(('enable','--now',self.f.config['unit'])),1)
        with self.assertRaises(ValueError):self.f.run('handoff')
    def test_go_is_never_cleared_or_accepted(self):
        self.f.artifacts();go=self.f.newroot/'owner-go.json';go.write_text('existing GO')
        with self.assertRaisesRegex(ValueError,'GO_PRESENT'):self.f.run('rollback')
        self.assertEqual(go.read_text(),'existing GO');self.assertEqual(self.f.calls,[])
    def test_unknown_inhibitor_is_not_removed(self):
        self.f.artifacts();self.f.drop.write_text('foreign')
        with self.assertRaises(ValueError):self.f.run('rollback')
        self.assertEqual(self.f.drop.read_text(),'foreign');self.assertEqual(self.f.calls,[])

    def test_handoff_and_rollback_prove_lease_keep_inode_and_history(self):
        history=self.f.oldroot/'claims';history.mkdir();claim=history/'spent.json';claim.write_text('immutable SPENT')
        halt=self.f.oldroot/'HALT';halt.write_text('original HALT')
        r=self.f.run('handoff')
        self.assertEqual(r['status'],'PUMP4_ORDERS_OFF_SELECTED')
        self.assertEqual(r['startup_proof']['pid'],os.getpid())
        self.assertEqual(r['broker_writes'],0)
        with self.assertRaises(BlockingIOError):AccountLease(self.f.lock)
        r=self.f.run('rollback')
        self.assertEqual(r['status'],'ORIGINAL_OWNER_RESTORED_ORDERS_OFF')
        self.assertEqual(r['startup_proof']['phase'],'TERMINAL')
        self.assertEqual(self.f.lock.stat().st_ino,self.f.inode)
        self.assertEqual(claim.read_text(),'immutable SPENT');self.assertEqual(halt.read_text(),'original HALT')
        self.assertTrue(self.f.fragment.exists());self.assertTrue(self.f.marker.exists())
        self.assertFalse((self.f.newroot/'owner-go.json').exists())
    def test_marker_only_old_active_recovery(self):
        self.f.artifacts(drop=False)
        self.assertEqual(self.f.run('rollback')['status'],'ORIGINAL_OWNER_RESTORED_ORDERS_OFF')
    def test_rollback_old_start_failure_has_no_success_receipt_and_can_recover(self):
        self.f.artifacts();self.f.stop_old();self.f.old_start_failure=True
        with self.assertRaisesRegex(ValueError,'STARTUP'):self.f.run('rollback')
        self.assertFalse(self.f.drop.exists());self.assertTrue(self.f.marker.exists())
        self.assertEqual(list(self.f.root.glob('handoff-*.json')),[])
        self.f.old_start_failure=False
        self.assertEqual(self.f.run('rollback')['status'],'ORIGINAL_OWNER_RESTORED_ORDERS_OFF')
    def test_live_pid_without_account_lock_cannot_succeed(self):
        real=self.f.systemctl
        def control(*args):
            r=real(*args)
            if args==('enable','--now',self.f.config['unit']):self.f.lease.close();self.f.lease=None
            return r
        with patch.object(m,'systemctl',control):
            with self.assertRaisesRegex(ValueError,'STARTUP'):self.f.run('handoff')
    def test_stale_wrong_pid_or_wrong_config_receipt_cannot_succeed(self):
        for changes in (dict(observed_ms=1),dict(pid=-1),dict(runner_config_sha256='foreign'),dict(scope_sha256='foreign'),dict(result=dict(status='BLOCKED_OBSERVATION'))):
            with self.subTest(changes=changes):
                f=Fixture()
                try:
                    real=f.systemctl
                    def control(*args):
                        r=real(*args)
                        if args==('enable','--now',f.config['unit']):
                            p=f.newroot/'supervisor/receipts/fixture-1.json';row=json.loads(p.read_bytes());row.update(changes);p.write_text(json.dumps(row))
                        return r
                    with patch.object(m,'systemctl',control):
                        with self.assertRaisesRegex(ValueError,'STARTUP'):f.run('handoff')
                finally:f.close()
    def test_later_fresh_tick_of_same_selected_pid_is_acceptable(self):
        real=self.f.systemctl
        def control(*args):
            r=real(*args)
            if args==('enable','--now',self.f.config['unit']):
                p=self.f.newroot/'supervisor/receipts/fixture-1.json';row=json.loads(p.read_bytes());row['tick']=3;p.write_text(json.dumps(row))
            return r
        with patch.object(m,'systemctl',control):self.assertEqual(self.f.run('handoff')['startup_proof']['tick'],3)
    def test_systemd_restart_policy_or_restart_count_rejected(self):
        for changes in (dict(Restart='on-failure'),dict(NRestarts='1')):
            with self.subTest(changes=changes):
                f=Fixture()
                try:
                    f.newstate.update(changes)
                    with self.assertRaisesRegex(ValueError,'STARTUP'):f.run('handoff')
                    self.assertEqual(f.calls.count(('enable','--now',f.config['unit'])),1)
                finally:f.close()
    def test_explicit_rollback_again_does_not_restart_active_original(self):
        self.f.run('handoff');self.f.run('rollback');lease=self.f.lease
        self.f.run('rollback')
        self.assertIs(self.f.lease,lease)
        self.assertEqual(self.f.calls.count(('disable','--now',self.f.old['unit'])),1)
    def test_failed_restored_heartbeat_is_not_success(self):
        self.f.artifacts();self.f.stop_old()
        with patch.object(self.f,'refresh_heartbeat',lambda:None):
            h=self.f.oldroot/'heartbeat.json';row=json.loads(h.read_bytes());row['at_ms']=1;h.write_text(json.dumps(row))
            with self.assertRaisesRegex(ValueError,'STARTUP'):self.f.run('rollback')
    def test_unknown_marker_unit_or_dropin_is_not_accepted(self):
        for kind in ('marker','unit','dropin'):
            with self.subTest(kind=kind):
                f=Fixture()
                try:
                    f.artifacts()
                    if kind=='marker':f.marker.write_text('foreign')
                    elif kind=='unit':f.fragment.write_text('foreign')
                    else:(f.drop.parent/'99-unknown.conf').write_text('foreign')
                    with self.assertRaises(ValueError):f.run('rollback')
                    self.assertEqual(f.calls,[])
                finally:f.close()
    def test_no_marker_is_not_a_rollback_authorization(self):
        self.f.stop_old()
        with self.assertRaisesRegex(ValueError,'ROLLBACK_MARKER'):self.f.run('rollback')
        self.assertEqual(self.f.calls,[])
    def test_dangling_go_symlink_blocks_without_modification(self):
        self.f.artifacts();go=self.f.newroot/'owner-go.json';go.symlink_to(self.f.root/'absent')
        with self.assertRaisesRegex(ValueError,'GO_PRESENT'):self.f.run('rollback')
        self.assertTrue(go.is_symlink());self.assertEqual(self.f.calls,[])
    def test_nonflat_account_blocks_before_physical_mutations(self):
        with patch.object(bybit,'flat_account',lambda *a,**k:dict(positions_flat=False,open_orders_empty=True)):
            with self.assertRaisesRegex(ValueError,'ACCOUNT_NOT_FLAT'):self.f.run('handoff')
        self.assertEqual(self.f.calls,[]);self.assertFalse(self.f.marker.exists())
    def test_go_arriving_during_get_blocks_before_physical_mutations(self):
        def account(*a,**k):
            (self.f.newroot/'owner-go.json').write_text('late GO');return {},{}
        with patch.object(self.f,'flat',account):
            with self.assertRaisesRegex(ValueError,'GO_PRESENT'):self.f.run('handoff')
        self.assertEqual(self.f.calls,[]);self.assertFalse(self.f.marker.exists())
        self.assertEqual((self.f.newroot/'owner-go.json').read_text(),'late GO')
    def test_pending_original_command_blocks(self):
        commands=self.f.oldroot/'commands';commands.mkdir();(commands/'pending.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'PENDING_OLD_COMMAND'):self.f.run('handoff')
        self.assertFalse(self.f.marker.exists());self.assertEqual(self.f.calls,[])
    def test_inspect_is_get_only_and_does_not_change_unit_or_lease(self):
        r=self.f.run('inspect')
        self.assertEqual(r['financial_units_changed'],0);self.assertEqual(self.f.calls,[])
        self.assertEqual(self.f.gets,1);self.assertFalse(self.f.marker.exists())
        with self.assertRaises(BlockingIOError):AccountLease(self.f.lock)


class LockParserTests(unittest.TestCase):
    def test_only_exact_flock_pid_device_and_inode_is_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);lock=root/'account.lock';lease=AccountLease(lock)
            try:
                locks=root/'locks';st=lock.stat();identity=f'{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}'
                for row,expected in ((f'1: FLOCK ADVISORY WRITE {os.getpid()} {identity} 0 EOF',True),
                    (f'1: FLOCK ADVISORY WRITE -1 {identity} 0 EOF',False),
                    (f'1: POSIX ADVISORY WRITE {os.getpid()} {identity} 0 EOF',False),
                    (f'1: -> FLOCK ADVISORY WRITE {os.getpid()} {identity} 0 EOF',False),
                    (f'1: FLOCK ADVISORY WRITE {os.getpid()} 00:00:1 0 EOF',False)):
                    locks.write_text(row+'\n')
                    with patch.object(m,'PROC_LOCKS',locks):self.assertEqual(m.lock_held_by(lock,os.getpid()),expected)
            finally:lease.close()

if __name__=='__main__':unittest.main(verbosity=2)
