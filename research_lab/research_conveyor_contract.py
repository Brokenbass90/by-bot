"""Strict, research-only manifest and receipt primitives for Conveyor V1."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import copy
import re
from types import MappingProxyType
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


AUTHORITY = "research_only_no_live_risk_order_promotion_or_private_api_authority"
MANIFEST_SCHEMA = "research_conveyor_manifest_v1"


class ContractError(ValueError):
    """Input is not safe or complete enough for research execution."""


def _object(data: Any, allowed: set[str], label: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ContractError(f"{label} must be an object")
    extra = set(data) - allowed
    if extra:
        raise ContractError(f"{label} unknown fields: {sorted(extra)}")
    return data


def _canonical(data: Any) -> bytes:
    try:
        return json.dumps(data, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ContractError("non-canonical JSON payload") from exc


def _sha(data: Any) -> str:
    return hashlib.sha256(_canonical(data)).hexdigest()


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return copy.deepcopy(value)

def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _load_json(path: Path) -> Any:
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ContractError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except ContractError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read JSON: {path}") from exc


def _inside(root: Path, value: str, *, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts or any(ch in value for ch in "*?[]"):
        raise ContractError(f"{label} must be an explicit relative path")
    raw = Path(value)
    root = root.resolve()
    current = root
    for part in raw.parts:
        current /= part
        if current.is_symlink():
            raise ContractError(f"{label} contains symlink component")
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ContractError(f"{label} escapes repository root") from exc
    return candidate


@dataclass(frozen=True)
class ConveyorManifest:
    root: Path
    path: Path
    _payload: Mapping[str, Any]
    sha256: str

    @property
    def hypotheses(self) -> tuple[dict[str, Any], ...]:
        return tuple(_thaw(h) for h in self._payload["hypotheses"])

    @property
    def payload(self) -> dict[str, Any]:
        return _thaw(self._payload)


_TOP = {"schema_id", "authority", "enabled", "max_jobs_per_run", "max_runtime_seconds", "min_free_bytes", "allowed_script_roots", "hypotheses"}
_HYP = {"id", "title", "market", "family", "priority", "state", "reopen_when", "contract_refs", "data_refs", "preregistration", "adapters"}
_PREREG = {"hypothesis", "universe", "signal", "entry", "exit", "costs", "control", "stress", "concentration", "death_criteria", "acceptance_gate"}
_DATA = {"path", "min_count", "sha256"}
_PHASES = ("prereg", "replay", "random_control", "stress")
_STATES = {"RUNNABLE", "BLOCKED_ADAPTER", "BLOCKED_DATA_OR_PARITY", "DISABLED"}
_HYPOTHESIS_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


def _data_fingerprint(path: Path) -> tuple[str, int]:
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest(), 1
    files = sorted(p for p in path.rglob("*") if p.is_file())
    entries = [{"path": str(p.relative_to(path)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    return _sha(entries), len(files)


def load_manifest(root: Path, path: Path) -> ConveyorManifest:
    root, path = Path(root).resolve(), Path(path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ContractError("manifest escapes repository root") from exc
    raw = _object(_load_json(path), _TOP, "manifest")
    if raw.get("schema_id") != MANIFEST_SCHEMA or raw.get("authority") != AUTHORITY:
        raise ContractError("wrong schema or authority")
    if not isinstance(raw.get("enabled"), bool):
        raise ContractError("enabled must be boolean")
    for field in ("max_jobs_per_run", "max_runtime_seconds", "min_free_bytes"):
        if isinstance(raw.get(field), bool) or not isinstance(raw.get(field), int) or raw[field] <= 0:
            raise ContractError(f"{field} must be a positive integer")
    roots = raw.get("allowed_script_roots")
    if not isinstance(roots, list) or not roots or any(not isinstance(x, str) or x not in {"research_lab", "scripts"} for x in roots):
        raise ContractError("allowed_script_roots must be an explicit allowlist")
    hypotheses = raw.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        raise ContractError("hypotheses must be non-empty")
    ids = set()
    for i, item in enumerate(hypotheses):
        h = _object(item, _HYP, f"hypotheses[{i}]")
        hid = h.get("id")
        if not isinstance(hid, str) or not _HYPOTHESIS_ID.fullmatch(hid) or hid in ids:
            raise ContractError("hypothesis IDs must be unique safe path components")
        ids.add(hid)
        if not all(isinstance(h.get(k), str) and h[k] for k in ("title", "market", "family", "reopen_when")):
            raise ContractError(f"{hid} descriptive fields invalid")
        if isinstance(h.get("priority"), bool) or not isinstance(h.get("priority"), int):
            raise ContractError(f"{hid} priority invalid")
        if h.get("state") not in _STATES:
            raise ContractError(f"{hid} state invalid")
        refs = h.get("contract_refs")
        if not isinstance(refs, list) or not refs:
            raise ContractError(f"{hid} contract_refs required")
        for ref in refs:
            p = _inside(root, ref, label=f"{hid}.contract_refs")
            if not p.is_file():
                raise ContractError(f"missing contract ref: {ref}")
        data_refs = h.get("data_refs")
        if not isinstance(data_refs, list):
            raise ContractError(f"{hid} data_refs invalid")
        for d in data_refs:
            d = _object(d, _DATA, f"{hid}.data_ref")
            if set(d) != {"path", "min_count", "sha256"}:
                raise ContractError(f"{hid} data_ref requires path, min_count and sha256")
            p = _inside(root, d.get("path"), label=f"{hid}.data_ref.path")
            if not p.exists():
                raise ContractError(f"missing data ref: {d.get('path')}")
            if p.is_symlink() or any(x.is_symlink() for x in p.rglob("*")):
                raise ContractError(f"{hid} data ref contains symlink")
            if "min_count" in d and (isinstance(d["min_count"], bool) or not isinstance(d["min_count"], int) or d["min_count"] < 0):
                raise ContractError(f"{hid} min_count invalid")
            if not isinstance(d["sha256"], str) or not __import__("re").fullmatch(r"[0-9a-f]{64}", d["sha256"]):
                raise ContractError(f"{hid} data sha256 invalid")
            actual, count = _data_fingerprint(p)
            if count < d["min_count"] or actual != d["sha256"]:
                raise ContractError(f"{hid} data fingerprint/count mismatch")
        prereg = _object(h.get("preregistration"), _PREREG, f"{hid}.preregistration")
        if set(prereg) != _PREREG or any(not isinstance(v, str) or not v for v in prereg.values()):
            raise ContractError(f"{hid} preregistration incomplete")
        adapters = h.get("adapters")
        if h["state"] == "RUNNABLE":
            if not isinstance(adapters, dict) or set(adapters) != set(_PHASES):
                raise ContractError(f"{hid} runnable card needs all phases")
        elif adapters is not None:
            raise ContractError(f"{hid} blocked card must not declare adapters")
        if adapters is not None:
            for phase in _PHASES:
                argv = adapters[phase]
                if not isinstance(argv, list) or not argv or argv[0] != "{python}":
                    raise ContractError(f"{hid}.{phase} adapter must use current Python")
                if len(argv) < 2 or not isinstance(argv[1], str) or argv[1].startswith("-") or not argv[1].endswith(".py"):
                    raise ContractError(f"{hid}.{phase} adapter script missing")
                script = _inside(root, argv[1], label=f"{hid}.{phase}.script")
                allowed = [(root / r).resolve() for r in roots]
                if not script.is_file() or script.is_symlink() or not any(script.is_relative_to(base) for base in allowed):
                    raise ContractError(f"{hid}.{phase}.script not in allowed existing roots")
                if argv[1] not in refs:
                    raise ContractError(f"{hid}.{phase} adapter script must be a contract ref")
                for arg in argv[2:]:
                    if not isinstance(arg, str) or (arg.startswith("{") and arg not in {"{run_dir}", "{hypothesis_id}", "{phase}", "{receipt}"}):
                        raise ContractError(f"{hid}.{phase} unknown placeholder/argument")
    return ConveyorManifest(root, path, _freeze(copy.deepcopy(raw)), _sha(raw))


def freeze_hypothesis(root: Path, manifest: ConveyorManifest, hypothesis_id: str) -> dict[str, Any]:
    matches = [h for h in manifest.hypotheses if h["id"] == hypothesis_id]
    if len(matches) != 1:
        raise ContractError("unknown hypothesis")
    h = matches[0]
    if Path(root).resolve() != manifest.root:
        raise ContractError("freeze root differs from manifest root")
    contract_hashes = {ref: hashlib.sha256(_inside(root, ref, label="contract").read_bytes()).hexdigest() for ref in h["contract_refs"]}
    data_hashes = {d["path"]: {"sha256": d["sha256"], "actual_sha256": _data_fingerprint(_inside(root, d["path"], label="data"))[0], "min_count": d["min_count"]} for d in h["data_refs"]}
    if any(v["sha256"] != v["actual_sha256"] for v in data_hashes.values()):
        raise ContractError("data hash drift")
    return {"schema_id": "research_conveyor_hypothesis_freeze_v1", "authority": AUTHORITY, "hypothesis": h["id"], "manifest_sha256": manifest.sha256, "preregistration_sha256": _sha(h["preregistration"]), "contract_hashes": contract_hashes, "data_hashes": data_hashes}


def write_self_hashed_json(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(payload)
    if "receipt_sha256" in value:
        raise ContractError("payload must not contain receipt_sha256")
    if value.get("schema_id") == "x" and set(value) != {"schema_id", "value"}:
        raise ContractError("generic receipt unknown fields")
    value["receipt_sha256"] = _sha(value)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(_canonical(value).decode("ascii") + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return value


def read_verified_receipt(path: Path, *, expected_schema: str) -> dict[str, Any]:
    value = _load_json(Path(path))
    if expected_schema == "x":
        allowed = {"schema_id", "receipt_sha256", "value"}
    else:
        allowed = {"schema_id", "receipt_sha256", "authority", "hypothesis_id", "phase", "status", "manifest_sha256", "preregistration_sha256", "adapter_argv_sha256", "input_artifacts", "output_artifacts", "metrics", "live_or_broker_calls", "private_api_calls", "capital_or_promotion_authority"}
    value = _object(value, allowed, "receipt")
    required = {"schema_id", "receipt_sha256", "value"} if expected_schema == "x" else allowed
    if not required.issubset(value):
        raise ContractError("receipt missing required fields")
    if value.get("schema_id") != expected_schema or not isinstance(value.get("receipt_sha256"), str):
        raise ContractError("receipt schema or hash missing")
    supplied = value["receipt_sha256"]
    unsigned = {k: v for k, v in value.items() if k != "receipt_sha256"}
    if supplied != _sha(unsigned):
        raise ContractError("receipt hash mismatch")
    return value
