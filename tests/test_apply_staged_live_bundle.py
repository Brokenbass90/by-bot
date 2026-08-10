from pathlib import PurePosixPath

from scripts.apply_staged_live_bundle import (
    apply_files,
    backup_live_files,
    rollback_files,
)


def test_apply_and_rollback_preserve_originally_absent_files(tmp_path):
    live = tmp_path / "live"
    stage = tmp_path / "stage"
    backup = tmp_path / "backup"
    paths = [PurePosixPath("main.py"), PurePosixPath("bot/new_dep.py")]

    live.mkdir()
    stage.joinpath("bot").mkdir(parents=True)
    live.joinpath("main.py").write_text("old\n", encoding="utf-8")
    stage.joinpath("main.py").write_text("new\n", encoding="utf-8")
    stage.joinpath("bot/new_dep.py").write_text("dependency\n", encoding="utf-8")

    absent = backup_live_files(live_root=live, backup_root=backup, paths=paths)
    assert absent == ["bot/new_dep.py"]

    apply_files(live_root=live, stage_root=stage, paths=paths, token="test")
    assert live.joinpath("main.py").read_text(encoding="utf-8") == "new\n"
    assert live.joinpath("bot/new_dep.py").read_text(encoding="utf-8") == "dependency\n"

    rollback_files(
        live_root=live,
        backup_root=backup,
        paths=paths,
        originally_absent=set(absent),
    )
    assert live.joinpath("main.py").read_text(encoding="utf-8") == "old\n"
    assert not live.joinpath("bot/new_dep.py").exists()
