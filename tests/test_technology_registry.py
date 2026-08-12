from pathlib import Path

from scripts.build_tech_registry import build_registry, compact_registry


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_registry_separates_static_reachability_from_test_mentions(tmp_path: Path) -> None:
    _write(
        tmp_path / "smart_pump_reversal_bot.py",
        "from bot.live_bridge import run\n",
    )
    _write(
        tmp_path / "bot" / "live_bridge.py",
        '"""Live bridge."""\nfrom bot.shared_level import score\n\ndef run(): return score()\n',
    )
    _write(
        tmp_path / "bot" / "shared_level.py",
        '"""Shared level scorer."""\ndef score(): return 1\n',
    )
    _write(
        tmp_path / "bot" / "orphan_tool.py",
        '"""Research helper."""\ndef probe(): return 1\n',
    )
    _write(
        tmp_path / "tests" / "test_orphan_tool.py",
        "from bot.orphan_tool import probe\n",
    )

    payload = build_registry(root=tmp_path)
    rows = {row["name"]: row for row in payload["modules"]}

    assert rows["live_bridge"]["direct_monolith_reference"] is True
    assert rows["shared_level"]["static_runtime_reachable"] is True
    assert rows["orphan_tool"]["static_runtime_reachable"] is False
    assert rows["orphan_tool"]["inventory_status"] == "tested_static_runtime_not_observed"
    assert payload["authority"] == "static_inventory_not_promotion_evidence"


def test_compact_registry_keeps_warning_and_bounded_candidates(tmp_path: Path) -> None:
    _write(tmp_path / "smart_pump_reversal_bot.py", "")
    for index in range(4):
        _write(
            tmp_path / "bot" / f"tool_{index}.py",
            f'"""Tool {index}."""\ndef run(): return {index}\n',
        )
        _write(
            tmp_path / "tests" / f"test_tool_{index}.py",
            f"from bot.tool_{index} import run\n",
        )

    compact = compact_registry(build_registry(root=tmp_path), limit=2)

    assert len(compact["tested_static_runtime_not_observed"]) == 2
    assert len(compact["not_wired_catalog"]) == 4
    assert {row["name"] for row in compact["not_wired_catalog"]} == {
        "tool_0", "tool_1", "tool_2", "tool_3",
    }
    assert compact["wired_names"] == []
    assert "не доказательство пользы" in compact["reading_guide"]
    assert compact["warnings"]
