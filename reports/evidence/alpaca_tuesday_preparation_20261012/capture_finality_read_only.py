"""One bounded October13 GET-only observation of the original NET lifecycle.

Extends the published post-entry reader with complete activity-source requests.
Never runs the opener/guard, reserves, submits, reprices, restarts or clears HALT.
An activity page with 100 rows is explicitly incomplete, never a zero-fee proof.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'reports/evidence/alpaca_net_paper_20261012/capture_post_attempt.py'
SOURCE_PIN = 'ce84d4f650ecce079ea3555134e36a76f9bb8df5b52aaefd6b6e7b14f8de3b51'
EARLIEST_MS = 1791898500000  # Original Oct13 13:35 UTC unwind-not-before.


def query():
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SOURCE_PIN
    spec = importlib.util.spec_from_file_location('published_net_get_reader', SOURCE)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    old = "assert time.time_ns()//1000000 >= 1791812100000, 'POST_WINDOW_ONLY'"
    assert module.REMOTE.count(old) == 1
    remote = module.REMOTE.replace(old, f"assert time.time_ns()//1000000 >= {EARLIEST_MS}, 'OCT13_POST_UNWIND_ONLY'")
    old_paths = "paths={'account':'/v2/account','positions':'/v2/positions',"
    assert remote.count(old_paths) == 1
    remote = remote.replace(old_paths, "paths={'activities':'/v2/account/activities?after=2026-10-12T00%3A00%3A00Z&direction=asc&page_size=100'," + old_paths[len('paths={'):])
    assert "method='GET'" in remote and 'submit_' not in remote and 'cancel_' not in remote
    return remote


def main(output):
    assert time.time_ns() // 1000000 >= EARLIEST_MS, 'OCT13_POST_UNWIND_ONLY'
    output = output.absolute()
    assert output.parent == ROOT / '.private/alpaca_net_paper_20261012', 'PRIVATE_CAPTURE_DIRECTORY_ONLY'
    assert not any(p.is_symlink() for p in (output, *output.parents)), 'PRIVATE_CAPTURE_SYMLINK'
    assert output.parent.is_dir() and not output.exists()
    remote = query()
    call = subprocess.run(['ssh', '-i', str(Path.home()/'.ssh/by-bot'),
        '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
        'root@64.226.73.119', '/root/by-bot/.venv/bin/python -B -'],
        input=remote.encode(), capture_output=True, timeout=100)
    if call.returncode:
        print('READBACK_FAILED exit=' + str(call.returncode), file=sys.stderr)
        raise SystemExit(call.returncode)
    assert len(call.stdout) < 5000000
    response = json.loads(call.stdout)
    response['activity_source_pages'] = {}
    for label in ('paper', 'live'):
        source = response[label + '_broker']['activities']
        rows = source.get('payload')
        response['activity_source_pages'][label] = dict(http_status=source['http_status'],
            rows=len(rows) if isinstance(rows, list) else None,
            bounded_page_complete=isinstance(rows, list) and len(rows)<100,
            zero_fees_proven=False, publication_finality_proven=False)
    capture = dict(query_sha256=hashlib.sha256(remote.encode()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        original_reader_sha256=SOURCE_PIN, response=response)
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(capture, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(capture_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        observed_ms=response['observed_ms'], broker_writes=0, remote_writes=0,
        app_mismatches=response['app_manifest']['mismatches'],
        activity_pages=response['activity_source_pages'])))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
