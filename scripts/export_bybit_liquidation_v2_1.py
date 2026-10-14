#!/usr/bin/env python3
"""Create-exclusive read-only normalized snapshot, without source/eligibility changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import uuid


def encoded(value): return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
def sha(value): return hashlib.sha256(value).hexdigest()


def export(root, output):
    root = Path(root).absolute(); output = Path(output).absolute()
    if output.parent != root / "exports" or any(p.is_symlink() for p in (root,output,*output.parents)):
        raise ValueError("EXPORT_PATH_OUTSIDE_OWN_ROOT_OR_SYMLINK")
    receipt_path = output.with_suffix(".receipt.json")
    if output.exists() or receipt_path.exists(): raise FileExistsError("EXPORT_ALREADY_SEALED")
    manifest = json.loads((root / "source-manifest.json").read_bytes())
    claim = manifest["manifest_sha256"]
    if sha(encoded({k:v for k,v in manifest.items() if k!="manifest_sha256"})) != claim:
        raise ValueError("SOURCE_MANIFEST_HASH_INVALID")
    if manifest["normalized_schema"] != "BYBIT_ALL_LIQUIDATION_SOURCE_V2":
        raise ValueError("NOT_V2_SOURCE")
    output.parent.mkdir(mode=0o700,exist_ok=True)
    temporary = output.parent / ("." + output.name + "." + uuid.uuid4().hex + ".incomplete")
    fd = os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    count = 0; prefixes = {}; output_digest = hashlib.sha256()
    with os.fdopen(fd,"wb") as out:
        for path in sorted(root.glob("runs/*/frames.jsonl")):
            if path.is_symlink() or path.parent.is_symlink(): raise ValueError("SOURCE_SYMLINK")
            prefix = hashlib.sha256(); previous = "0"*64; byte_count = 0
            with path.open("rb") as source:
                while True:
                    line = source.readline(16*1024**2+1)
                    if not line: break
                    if len(line) > 16*1024**2: raise ValueError("SOURCE_RECORD_RESOURCE_BOUND")
                    if not line.endswith(b"\n"): break
                    row = json.loads(line)
                    claimed = row.get("record_sha256")
                    if (row.get("prev_sha256") != previous
                            or row.get("source_manifest_sha256") != claim
                            or sha(encoded({k:v for k,v in row.items() if k!="record_sha256"})) != claimed):
                        raise ValueError("SOURCE_CHAIN_INVALID")
                    previous = claimed; prefix.update(line); byte_count += len(line)
                    for event in row.get("normalized_events", []):
                        if event["schema"] != "BYBIT_ALL_LIQUIDATION_SOURCE_V2" or event["source_manifest_sha256"] != claim:
                            raise ValueError("NORMALIZED_SOURCE_INVALID")
                        data = encoded(event)+b"\n"; out.write(data); output_digest.update(data); count += 1
            prefixes[str(path.relative_to(root))] = dict(bytes=byte_count,sha256=prefix.hexdigest(),tip=previous)
        out.flush(); os.fsync(out.fileno())
    os.link(temporary,output); temporary.unlink(); os.chmod(output,0o400)
    receipt = dict(schema="BYBIT_LIQUIDATION_NORMALIZED_READONLY_EXPORT_V2_1",
                   status="SOURCE_EXPORT_ONLY_NOT_RESEARCH_READY", exported_ms=time.time_ns()//1000000,
                   normalized_path=str(output),normalized_sha256=output_digest.hexdigest(),event_count=count,
                   source_manifest_sha256=claim,epoch_id=manifest["epoch_id"],symbols=manifest["symbols"],
                   source_prefixes=prefixes,duplicate_policy="ALL_CANDIDATES_RETAINED_NO_ELIGIBILITY_DECISION",
                   full_exchange_coverage="UNKNOWN_NO_SEQUENCE_OR_BACKFILL",source_gate_pass=False,
                   strategy_runs=0,judge_runs=0,orders_allowed=False)
    receipt["receipt_sha256"] = sha(encoded(receipt))
    fd = os.open(receipt_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,"wb") as stream:stream.write(encoded(receipt)+b"\n");stream.flush();os.fsync(stream.fileno())
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(export(args.root,args.output),sort_keys=True))


if __name__=="__main__":main()
