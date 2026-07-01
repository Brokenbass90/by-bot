"""Resumable research runs — survive Mac sleep / lid-close without losing work.

Long sweeps die if the machine sleeps or the process is killed. This makes any
sweep RESUMABLE: each finished unit is appended to a durable JSONL done-log; on
restart you compute what's still pending and continue from there. Combine with:
  * `caffeinate -dimsu <cmd>`   — stop the Mac sleeping mid-run;
  * `screen`/`nohup`            — survive terminal/SSH close;
  * this checkpoint             — resume the unfinished units if it dies anyway.

Pure stdlib; append-only + atomic-ish writes.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence


class Checkpoint:
    def __init__(self, path: str) -> None:
        self.path = path

    def records(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue                 # tolerate a half-written last line
        except FileNotFoundError:
            pass
        return out

    def done_keys(self) -> set:
        return {str(r.get("key")) for r in self.records() if "key" in r}

    def record(self, key: str, result: Any = None) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"key": str(key), "result": result}, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())                     # durable across a hard sleep/kill

    def pending(self, all_keys: Sequence[str]) -> List[str]:
        done = self.done_keys()
        seen = set()
        out = []
        for k in all_keys:
            k = str(k)
            if k not in done and k not in seen:
                seen.add(k); out.append(k)
        return out

    def results(self) -> Dict[str, Any]:
        return {str(r["key"]): r.get("result") for r in self.records() if "key" in r}


def run_resumable(all_keys: Sequence[str], work_fn, checkpoint: Checkpoint) -> Dict[str, Any]:
    """Run work_fn(key) for each not-yet-done key, recording results as we go.

    Safe to call again after a crash/sleep: already-done keys are skipped.
    """
    for key in checkpoint.pending(all_keys):
        result = work_fn(key)
        checkpoint.record(key, result)
    return checkpoint.results()
