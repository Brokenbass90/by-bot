#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zip the most recent backtest run directory.

Usage:
  python3 scripts/zip_latest_run.py backtest_runs latest_run.zip

Default:
  root=backtest_runs, out=latest_run.zip
"""
from __future__ import annotations
import os, sys, glob, zipfile

def _latest_run_dir(root: str) -> str:
    runs = [p for p in glob.glob(os.path.join(root, "*")) if os.path.isdir(p)]
    if not runs:
        raise SystemExit(f"No run dirs found under: {root}")
    runs.sort(key=os.path.getmtime, reverse=True)
    return runs[0]

def zip_dir(src_dir: str, out_zip: str) -> None:
    src_dir = os.path.abspath(src_dir)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(src_dir):
            for fn in files:
                p = os.path.join(root, fn)
                arc = os.path.relpath(p, os.path.dirname(src_dir))
                z.write(p, arcname=arc)

def main() -> None:
    root = sys.argv[1] if len(sys.argv) >= 2 else "backtest_runs"
    out_zip = sys.argv[2] if len(sys.argv) >= 3 else "latest_run.zip"
    run_dir = _latest_run_dir(root)
    zip_dir(run_dir, out_zip)
    print(f"Zipped: {run_dir} -> {out_zip}")

if __name__ == "__main__":
    main()
