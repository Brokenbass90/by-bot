from pathlib import Path

from scripts.chat_with_local_ai import SAFE_CONTEXT_FILES, build_project_context, verified_status_text


def test_project_context_reads_only_explicit_allowlist(tmp_path: Path) -> None:
    (tmp_path / "runtime/project_audit").mkdir(parents=True)
    (tmp_path / "runtime/project_audit/supervisor_status.json").write_text(
        '{"proposal_only": true}', encoding="utf-8"
    )
    (tmp_path / ".env").write_text("SECRET=must-not-leak", encoding="utf-8")

    context, sources = build_project_context(tmp_path)

    assert "proposal_only" in context
    assert "must-not-leak" not in context
    assert ".env" not in sources


def test_project_context_starts_with_machine_readable_fact_index(tmp_path: Path) -> None:
    (tmp_path / "runtime/project_audit").mkdir(parents=True)
    (tmp_path / "runtime/project_audit/supervisor_status.json").write_text(
        '{"last_success_utc":"2026-08-09T03:32:05+00:00","proposal_only":true}',
        encoding="utf-8",
    )

    context, _ = build_project_context(tmp_path)

    assert "FACT_INDEX=" in context
    assert "2026-08-09T03:32:05+00:00" in context
    assert '"whole_project_verified": false' in context
    assert '"liveness_after_fix_signals": 9' in context
    assert "retest window was added as seconds" in context


def test_context_allowlist_contains_no_environment_or_key_files() -> None:
    lowered = [path.lower() for path in SAFE_CONTEXT_FILES]

    assert all(".env" not in path for path in lowered)
    assert all("key" not in Path(path).name for path in lowered)


def test_verified_status_is_deterministic_and_conservative() -> None:
    status = verified_status_text()

    assert "Весь проект проверен: НЕТ" in status
    assert "tf_ts в ms" in status
    assert "PF 0.305" in status


def test_verified_status_reports_live_mirror_provenance(tmp_path: Path) -> None:
    context_dir = tmp_path / "runtime/live_mirror/ai_context"
    context_dir.mkdir(parents=True)
    (context_dir / "full_context.json").write_text(
        '{"generated_at_utc":"2026-08-09T05:10:02+00:00"}', encoding="utf-8"
    )
    manifest = tmp_path / "runtime/live_mirror/sync_bundle_manifest.json"
    manifest.write_text('{"status":"complete"}', encoding="utf-8")

    status = verified_status_text(tmp_path)

    assert "2026-08-09T05:10:02+00:00" in status
    assert "bundle status: complete" in status


def test_context_fact_index_contains_bounded_research_verdicts(tmp_path: Path) -> None:
    fx_path = tmp_path / "reports/research/fx_smart_grid_v2_20260809_initial/verdict.json"
    fx_path.parent.mkdir(parents=True)
    fx_path.write_text(
        '{"generated_at_utc":"2026-08-09T05:14:21Z",'
        '"decision":"FAIL_OR_REBUILD","live_authorized":false,'
        '"best_stress":{"trades":5}}',
        encoding="utf-8",
    )
    pair_path = tmp_path / "reports/research/pairs_statarb_v2_20260809_initial/verdict.json"
    pair_path.parent.mkdir(parents=True, exist_ok=True)
    pair_path.write_text(
        '{"generated_at_utc":"2026-08-09T05:18:49Z",'
        '"decision":"FAIL_OR_REBUILD","live_authorized":false,'
        '"best":{"trades":756}}',
        encoding="utf-8",
    )

    context, sources = build_project_context(tmp_path)

    assert "reports/research/fx_smart_grid_v2_20260809_initial/verdict.json" in sources
    assert "reports/research/pairs_statarb_v2_20260809_initial/verdict.json" in sources
    assert '"fx_smart_grid_v2"' in context
    assert '"pairs_statarb_v2"' in context
    assert '"trades": 756' in context
