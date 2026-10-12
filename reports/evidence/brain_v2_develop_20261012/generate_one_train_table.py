"""Run the exact frozen A2 generator in its pinned isolated source snapshot.

No filter, B3 main, strategy resimulation or new mathematical code.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys


def main():
    base=Path(__file__).resolve().parent
    manifest=json.loads((base/'source_manifest.json').read_text())
    cutoff=sys.argv[1]
    assert cutoff in manifest['cutoffs']
    root=Path(manifest['staging_root'])
    for row in manifest['files']:
        assert hashlib.sha256((root/row['path']).read_bytes()).hexdigest()==row['sha256'],row['path']
    tables=base/'tables';tables.mkdir(exist_ok=True)
    out=tables/f'MU_SIGMA_{cutoff}.json';receipt=base/f'train_generation_{cutoff}.json'
    assert not out.exists() and not receipt.exists(),'existing train receipt; no implicit overwrite'
    env={'PATH':os.environ.get('PATH',''),'PYTHONPATH':str(root),
         'PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0'}
    command=[sys.executable,str(root/'research_lab/brain_v2/mu_sigma.py'),
             '--cutoff',cutoff,'--out',str(out)]
    result=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True)
    integrity=all(hashlib.sha256((root/row['path']).read_bytes()).hexdigest()==row['sha256']
                  for row in manifest['files'])
    record=dict(schema='BRAIN_V2_EXACT_A2_TRAIN_GENERATION',cutoff=cutoff,command=command,
                manifest_sha256=manifest['sha256'],generator_sha256=manifest['generator_sha256'],
                exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr,
                source_integrity_after=integrity,filter_runs=0,orders_allowed=False)
    if out.exists():
        raw=out.read_bytes();table=json.loads(raw)
        record.update(table_sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),
                      populated_sleeves=sorted(table['nogi']),
                      missing_sleeves=sorted({'ATT1','SBR1','ASR1','ETS2','SF3','BOUNCE1'}-set(table['nogi'])))
    receipt.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:record.get(k) for k in ('cutoff','exit_code','table_sha256','missing_sleeves','source_integrity_after')}))
    assert result.returncode==0 and integrity


if __name__=='__main__':main()
