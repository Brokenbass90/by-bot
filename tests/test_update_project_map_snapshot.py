from datetime import datetime, timezone

from scripts.update_project_map_snapshot import END, START, build_snapshot, update_text


def test_update_text_replaces_existing_block():
    old = f"head\n\n{START}\nold\n{END}\n\ntail\n"
    new = update_text(old, f"{START}\nfresh\n{END}")
    assert "old" not in new
    assert "fresh" in new
    assert new.startswith("head")
    assert new.rstrip().endswith("tail")


def test_update_text_inserts_before_key_docs_when_missing():
    old = "# Map\n\n## Ключевые документы\n- a\n"
    new = update_text(old, f"{START}\nfresh\n{END}")
    assert new.index("fresh") < new.index("## Ключевые документы")


def test_build_snapshot_contains_stable_fields(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "strategies").mkdir()
    (tmp_path / "backtest").mkdir()
    (tmp_path / "bot").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "reports").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("", encoding="utf-8")
    (tmp_path / "strategies" / "s.py").write_text("", encoding="utf-8")
    (tmp_path / "backtest" / "b.py").write_text("", encoding="utf-8")
    (tmp_path / "bot" / "ai_tools.py").write_text("def get_project_map(): pass", encoding="utf-8")
    (tmp_path / "scripts" / "collect_bybit_liquidations.py").write_text("", encoding="utf-8")
    snap = build_snapshot(tmp_path, now=datetime(2026, 6, 16, tzinfo=timezone.utc))
    assert "generated_utc: `2026-06-16T00:00:00Z`" in snap
    assert "tests: `1`" in snap
    assert "onboard AI project-map tool: `yes`" in snap
