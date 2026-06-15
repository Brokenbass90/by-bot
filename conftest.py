"""Pytest configuration shared across the test suite.

Auto-marks the known memory/CPU-heavy backtest tests as ``slow`` so the fast
lane (``pytest -m "not slow"``) gives quick, low-memory feedback while the full
suite still runs them. Added 2026-06-14 during the intake audit.
"""

# Test modules that pull in the backtest engine / pandas-heavy optimization and
# are best isolated from the quick safety-rail lane.
_SLOW_TEST_FILES = {
    "test_pair_stat_arb.py",
    "test_validate_pair_arb.py",
    "test_pair_arb_executor.py",
    "test_pair_arb_scanner.py",
    "test_sweep_baseline_parity.py",
    "test_exact_backtest_cache.py",
    "test_robustness.py",
    "test_smart_grid.py",
}


def pytest_collection_modifyitems(config, items):
    import pytest

    slow = pytest.mark.slow
    for item in items:
        if item.path.name in _SLOW_TEST_FILES:
            item.add_marker(slow)
