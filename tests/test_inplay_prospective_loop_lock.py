from __future__ import annotations

from scripts.run_inplay_prospective_shadow_loop import acquire_single_instance


def test_single_instance_lock_fails_closed(tmp_path):
    path = tmp_path / "collector.flock"
    first = acquire_single_instance(path)
    assert first is not None
    try:
        assert acquire_single_instance(path) is None
    finally:
        first.close()

    recovered = acquire_single_instance(path)
    assert recovered is not None
    recovered.close()
