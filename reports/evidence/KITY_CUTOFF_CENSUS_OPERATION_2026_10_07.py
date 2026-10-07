"""One source-only operation using the unchanged approved public GET facade."""
from pathlib import Path
import hashlib, importlib.util, json, os, shutil, signal, subprocess, time

BASE=Path(__file__).resolve().parent
CUTOFF=1791417300000  # 2026-10-07T23:55:00Z; immutable
TARGET=CUTOFF-1800
SOURCE=BASE/'app/scripts/kity_m3_orders_off.py'
RUNTIME=BASE/'app/.private/kity_m3_orders_off'

def save(name, payload):
 raw=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
 with (RUNTIME/name).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 (RUNTIME/name).chmod(0o400)

def within_cutoff(capture):
 return CUTOFF-2000 <= capture['receive_ms'] <= CUTOFF and capture['request_ms'] <= capture['receive_ms']

def main():
 assert int(time.time_ns()//1000000)<TARGET,'MISSED_TARGET_NO_RETRY'
 manifest=json.loads((BASE/'source_manifest.json').read_text())
 assert all(hashlib.sha256((BASE/n).read_bytes()).hexdigest()==h for n,h in manifest.items())
 assert not any((RUNTIME/n).exists() for n in ['schedule.json','terminal.json','census-2026-10-08.json'])
 save('schedule.json',{'cutoff_ms':CUTOFF,'request_target_ms':TARGET,'deadline_ms':CUTOFF,
                      'automatic_retry':False,'broker_writes':0,'orders_allowed':False,'operation':'EXCHANGEINFO_SOURCE_ONLY'})
 while time.time_ns()//1000000<TARGET:
  time.sleep(min(30,max(.001,(TARGET-time.time_ns()//1000000)/1000)))
 try:
  assert time.time_ns()//1000000<CUTOFF,'FIXED_DEADLINE_PASSED'
  assert shutil.disk_usage(BASE).free>=512*1024*1024,'DISK_BOUND'
  assert subprocess.check_output(['timedatectl','show','--property=NTPSynchronized','--value'],text=True).strip()=='yes','CLOCK_SYNC_UNCONFIRMED'
  assert all(hashlib.sha256((BASE/n).read_bytes()).hexdigest()==h for n,h in manifest.items()),'SOURCE_CHANGED'
  signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('CAPTURE_15S_BOUND')))
  signal.alarm(15)
  spec=importlib.util.spec_from_file_location('source_facade',SOURCE);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  capture=module.get_public('BINANCE','/fapi/v1/exchangeInfo',{})
  signal.alarm(0)
  module._write_capture(str(RUNTIME/'census-2026-10-08.json'),capture)
  save('terminal.json',{'status':'CUTOFF_CENSUS_CAPTURED' if within_cutoff(capture) else 'BLOCKED_DATA',
       'reason':None if within_cutoff(capture) else 'RECEIVE_OUTSIDE_FROZEN_CUTOFF',
       'cutoff_ms':CUTOFF,'request_ms':capture['request_ms'],'receive_ms':capture['receive_ms'],
       'capture_sha256':hashlib.sha256((RUNTIME/'census-2026-10-08.json').read_bytes()).hexdigest(),
       'oi_collected':False,'signal_reconstructed':False,'broker_writes':0,'orders_allowed':False})
 except Exception as exc:
  signal.alarm(0)
  save('terminal.json',{'status':'BLOCKED_DATA','reason':type(exc).__name__+':'+str(exc),
       'observed_ms':time.time_ns()//1000000,'cutoff_ms':CUTOFF,'broker_writes':0,'orders_allowed':False})

if __name__=='__main__':main()
