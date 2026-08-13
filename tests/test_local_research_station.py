from __future__ import annotations

from pathlib import Path

import scripts.local_research_station as station


def test_screen_parser_excludes_dead_sockets() -> None:
    output = """There are screens on:\n\t67527.research_funding_frozen\t(Dead ???)\n\t51799.alpaca_adaptive_shadow_20260726\t(Detached)\n\t44263.project_audit_local_20260808\t(Dead ???)\n2 Sockets.\n"""

    assert station._parse_screen_sessions(output) == ["alpaca_adaptive_shadow_20260726"]


def test_job_requires_process_and_fresh_evidence(tmp_path: Path, monkeypatch) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    job = station.Job("fixture", "fixture", ("fixture",), "scripts/fixture_loop.sh", str(evidence), 60)
    monkeypatch.setattr(station, "ROOT", Path("/"))
    monkeypatch.setattr(station, "_matching_sessions", lambda job: ["fixture"])

    result = station.evaluate_job(job, now=evidence.stat().st_mtime + 30, start_missing=False)

    assert result["state"] == "healthy"
    assert result["process_alive"] is True
    assert result["evidence_fresh"] is True


def test_alive_process_with_stale_evidence_is_not_false_green(tmp_path: Path, monkeypatch) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    job = station.Job("fixture", "fixture", ("fixture",), "scripts/fixture_loop.sh", str(evidence), 60)
    monkeypatch.setattr(station, "ROOT", Path("/"))
    monkeypatch.setattr(station, "_matching_sessions", lambda job: ["fixture"])

    result = station.evaluate_job(job, now=evidence.stat().st_mtime + 61, start_missing=False)

    assert result["state"] == "degraded_stale_evidence"
    assert result["process_alive"] is True
    assert result["evidence_fresh"] is False


def test_fresh_evidence_without_process_is_not_false_green(tmp_path: Path, monkeypatch) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    job = station.Job("fixture", "fixture", ("fixture",), "scripts/fixture_loop.sh", str(evidence), 60)
    monkeypatch.setattr(station, "ROOT", Path("/"))
    monkeypatch.setattr(station, "_matching_sessions", lambda job: [])

    result = station.evaluate_job(job, now=evidence.stat().st_mtime + 1, start_missing=False)

    assert result["state"] == "stopped_with_fresh_evidence"
    assert result["process_alive"] is False


def test_xsec_health_uses_daily_decision_receipt() -> None:
    job = next(item for item in station.JOBS if item.name == "xsec_v3_shadow")

    assert job.evidence == "runtime/xsec_v3_shadow/decision_latest.json"
    assert job.max_age_seconds == 30 * 3600
