#!/usr/bin/env python3
"""Deliver PUMP4's bounded DATA publication index as an append-only Mac view."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOUR = 3_600_000
VPS = "root@64.226.73.119"
ROOT = Path("/opt/bybot-research/pump4-server-orders-off-20261023/candidate-7d8ae05dab162ec5/app/.private/pump4-supervisor-v1")
OWNER = Path("/opt/bybot-research/pump4-current-hour-repair-20261101/candidate-05f89618d8550664/runtime/tiny-source-repair-next-20261101/supervisor")
SCOPE = "2de0b6ec1992b1df56f2a92f764a4b206dec1fcecc78b244b7264a63d00d0970"
PINS = {
    "strategies/pump_fade_v4r.py": "cea7a2cc9151d22ddaf620428dc6b7734f6aa4051819145821a76cda2381792a",
    "strategies/signals.py": "5f9408f203f303853360dd79e31fe0893b6db95329abbd758401a89f3258755c",
}
DEFAULT_DEST = Path("/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/research_lab/data/pump4_live_signaly.jsonl")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def pairs(items):
    result = dict(items)
    require(len(result) == len(items), "DUPLICATE_JSON_KEY")
    return result


def checked_path(path):
    require(not any(p.is_symlink() for p in (path, *path.parents)), "SOURCE_SYMLINK")
    return path


def read(path):
    path = checked_path(path)
    before = path.stat()
    require(path.is_file() and before.st_size <= 5_000_000 and before.st_nlink == 1, "SOURCE_FILE")
    raw = path.read_bytes()
    after = path.stat()
    require((before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_ino, after.st_size, after.st_mtime_ns), "SOURCE_CHANGED")
    return json.loads(raw, object_pairs_hook=pairs), hashlib.sha256(raw).hexdigest()


def signal_from(publication, name, hour, now, publication_sha):
    require(publication.get("status") == "CLOSED_H1_INTAKE_PASS"
            and publication.get("mode") == "CURRENT_CLOSED_BAR"
            and publication.get("source_kind") == "CONFIRMED_WS_WITH_FROZEN_JOURNAL_PREFIX"
            and publication.get("orders_allowed") is False
            and publication.get("money_authority") is False
            and type(publication.get("broker_writes")) is int
            and publication["broker_writes"] == 0, "PUBLICATION_SCOPE")
    observations = publication["decisions"]
    require(len(observations) == 1, "PUBLICATION_CARDINALITY")
    observation = observations[0]
    decision = observation["decision"]
    sym, ts = decision["symbol"], decision["bar_open_ms"]
    require(re.fullmatch(r"[A-Z0-9]+USDT", sym) and name == sym + ".json"
            and publication["symbol"] == sym and publication["cursor_ms"] == ts
            and type(ts) is int and ts == hour - HOUR, "PUBLICATION_IDENTITY")
    require(observation.get("schema") == "PUMP4_DATA_DECISION_OBSERVATION_V1"
            and observation.get("mode") == "CURRENT_CLOSED_BAR"
            and observation.get("orders_allowed") is False
            and observation.get("money_authority") is False
            and decision.get("orders_allowed") is False and decision.get("money_authority") is False
            and decision["source_pins"] == PINS, "OBSERVATION_SCOPE")
    core = {k: decision[k] for k in ("domain_schema", "symbol", "bar_open_ms",
                                     "history_sha256", "source_pins", "signal")}
    ident = decision["decision_id"]
    require(core["domain_schema"] == "PUMP4_CLOSED_H1_INTAKE_V1"
            and ident == "pump4-" + digest(core), "DECISION_HASH")
    times = [hour, decision["available_ms"], decision["first_observed_ms"],
             publication["publication_completed_ms"], now]
    require(all(type(x) is int for x in times) and times == sorted(times)
            and publication["pair_received_ms"] == decision["available_ms"], "PUBLICATION_CLOCK")
    if decision["signal"] is None:
        return None
    offset = times[3] - hour
    status, reason = ("BLOCKED", "PUBLICATION_LATE_60S") if offset > 60_000 else (
        "UNKNOWN", "NO_DECISION_BOUND_FINANCIAL_PROOF")
    attempt_sha = None
    match = dict(scope_sha256=SCOPE, decision_id=ident)
    attempt = OWNER / "attempts" / (digest(match) + ".json")
    if checked_path(attempt).exists():
        value, attempt_sha = read(attempt)
        require(all(value.get(k) == x for k, x in match.items())
                and value.get("status") == "ATTEMPT_CONSUMED_BEFORE_ACCOUNT_READ", "ATTEMPT_BINDING")
        status, reason = "ATTEMPTED", "FINANCIAL_RESULT_UNPROVEN"
    return dict(sym=sym, ts_ms=ts, decision_hour_ms=hour, decision_id=ident,
                status=status, reason=reason, publication_sha256=publication_sha,
                publication_offset_ms=offset, attempt_sha256=attempt_sha)


def collect(day):
    date = dt.date.fromisoformat(day)
    require(date.isoformat() == day, "DATE_FORMAT")
    begin = int(dt.datetime.combine(date, dt.time(), dt.timezone.utc).timestamp() * 1000)
    now = time.time_ns() // 1_000_000
    require(begin + 24 * HOUR + 120_000 <= now, "DAY_NOT_FINALIZED")
    rows, hours = [], []
    for hour in range(begin + HOUR, begin + 25 * HOUR, HOUR):
        folder = checked_path(ROOT / "ws-hours" / str(hour))
        files = sorted(checked_path(folder / "published").glob("*.json"))
        require(len(files) <= 137, "PUBLICATION_BOUND")
        summary = dict(hour_open_ms=hour, publications=len(files), status="MISSING" if not files else "PARTIAL")
        census_path = checked_path(folder / "receipt.json")
        census = None
        if census_path.is_file():
            census, summary["receipt_sha256"] = read(census_path)
            require(census.get("schema") == "PUMP4_WS_FULL137_DATA_RECEIPT_V1"
                    and census.get("source_hour_open_ms") == hour, "CENSUS_BINDING")
            summary["status"] = "PARTIAL"
        expected = {}
        if census is not None:
            for row in census["rows"]:
                if row.get("status") == "CLOSED_H1_INTAKE_PASS":
                    require(row["symbol"] not in expected, "CENSUS_DUPLICATE")
                    expected[row["symbol"]] = row
        same_index = set(expected) == {p.stem for p in files}
        for p in files:
            value, proof = read(p)
            same_index = same_index and expected.get(p.stem) == value
            row = signal_from(value, p.name, hour, now, proof)
            if row is not None:
                rows.append(row)
        if census is not None and files and same_index and census.get("hour_pass") is True                 and census.get("disconnected") is False and census.get("census") == 137                 and len(census["rows"]) == len({r["symbol"] for r in census["rows"]}) == 137                 and all(census.get(k) == len(files) for k in ("expected_trading", "complete_pairs", "within60s")):
            summary["status"] = "COMPLETE"
        hours.append(summary)
    return dict(schema="PUMP4_LIVE_RAW_SIGNAL_EXPORT_V1", day=day, observed_ms=now,
                hours=hours, rows=rows, coverage_complete=all(h["status"] == "COMPLETE" for h in hours))


def atomic(path, raw):
    checked_path(path)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as fp:
        temp = Path(fp.name)
        try:
            fp.write(raw)
            fp.flush()
            os.fsync(fp.fileno())
            fp.close()
            os.replace(temp, path)
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            temp.unlink(missing_ok=True)


def import_day(dest, payload):
    require(payload["schema"] == "PUMP4_LIVE_RAW_SIGNAL_EXPORT_V1"
            and len(payload["hours"]) == 24, "EXPORT_SCHEMA")
    checked_path(dest)
    coverage = dest.with_suffix(".coverage.json")
    fd = os.open(dest.with_suffix(".export.lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old = dest.read_bytes() if dest.exists() else b""
        require(len(old) <= 20_000_000 and (not old or old.endswith(b"\n")), "LOCAL_PREFIX")
        seen = {}
        for line in old.splitlines():
            row = json.loads(line, object_pairs_hook=pairs)
            ident = row["decision_id"]
            require(ident not in seen, "LOCAL_DUPLICATE")
            seen[ident] = {k: v for k, v in row.items() if k != "known_since_ms"}
        new = []
        now = time.time_ns() // 1_000_000
        for row in payload["rows"]:
            ident = row["decision_id"]
            if ident in seen:
                require(seen[ident] == row, "SIGNAL_CONFLICT_NO_OVERWRITE")
                continue
            seen[ident] = row
            new.append(canonical(dict(row, known_since_ms=now)) + b"\n")
        ledger = read(coverage)[0] if checked_path(coverage).exists() else {"days": {}}
        previous = ledger["days"].get(payload["day"])
        summary = {k: v for k, v in payload.items() if k != "rows"}
        summary.update(raw_signals=len(payload["rows"]), imported_ms=now,
                       first_imported_ms=previous.get("first_imported_ms", previous["imported_ms"]) if previous else now)
        if previous and previous["coverage_complete"]:
            require(previous["hours"] == summary["hours"] and previous["raw_signals"] == summary["raw_signals"],
                    "FINAL_DAY_DRIFT")
        if new or not dest.exists():
            atomic(dest, old + b"".join(new))
        if not previous or any(previous.get(k) != summary[k] for k in ("hours", "coverage_complete", "raw_signals")):
            ledger["days"][payload["day"]] = summary
            atomic(coverage, canonical(ledger) + b"\n")
        return dict(day=payload["day"], new=len(new), raw=len(payload["rows"]),
                    complete_hours=sum(x["status"] == "COMPLETE" for x in payload["hours"]),
                    missing_hours=sum(x["status"] == "MISSING" for x in payload["hours"]),
                    coverage_complete=payload["coverage_complete"])
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", action="append")
    parser.add_argument("--identity", type=Path, default=Path("/Users/nikolay.bulgakov/.ssh/by-bot"))
    parser.add_argument("--remote-read", action="store_true")
    parser.add_argument("--catchup", action="store_true")
    args = parser.parse_args()
    yesterday = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
    days = args.day or [yesterday.isoformat()]
    if args.catchup:
        require(not args.remote_read and not args.day, "CATCHUP_LOCAL_ONLY")
        coverage = checked_path(DEFAULT_DEST.with_suffix(".coverage.json"))
        known = read(coverage)[0]["days"] if coverage.exists() else {}
        start = dt.date(2026, 11, 5)
        days = []
        for i in range(max(0, (yesterday - start).days + 1)):
            day = (start + dt.timedelta(days=i)).isoformat()
            if day not in known:
                days.append(day)
                if len(days) == 3:
                    break
        if not days:
            print(json.dumps(dict(status="NO_NEW_FINALIZED_DAY")))
            return
    require(1 <= len(days) <= 3 and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in days), "DAY_BOUND")
    if args.remote_read:
        print(json.dumps([collect(day) for day in days], allow_nan=False))
        return
    command = ["ssh", "-i", str(args.identity), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "ConnectTimeout=15", VPS, "python3 -B - --remote-read " + " ".join("--day " + d for d in days)]
    result = subprocess.run(command, input=Path(__file__).read_bytes(), capture_output=True, timeout=180)
    if result.returncode:
        reason = re.search(rb"(?m)^ValueError: ([A-Z_0-9]+)$", result.stderr)
        label = reason.group(1).decode() if reason else "SSH_OR_SOURCE_ERROR"
        raise ValueError(label)
    require(len(result.stdout) <= 3_000_000, "EXPORT_BOUND")
    values = json.loads(result.stdout, object_pairs_hook=pairs)
    require([x["day"] for x in values] == days, "EXPORT_DAY_BINDING")
    for payload in values:
        print(json.dumps(import_day(DEFAULT_DEST, payload), sort_keys=True))


if __name__ == "__main__":
    main()
