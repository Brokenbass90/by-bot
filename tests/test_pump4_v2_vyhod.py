"""PUMP4 V2 выход (prereg PREREG_PUMP4_V2_VYHOD_2026_10_20): безубыток после первой цели со следующего бара, вторая цель 0.9R."""
import importlib.util, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "research_lab"))


def _pp():
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location("pp", ROOT / "research_lab" / "pump4_pereschet.py")
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
    finally:
        os.chdir(cwd)


def test_v2_bezubytok_so_sleduyushchego_bara():
    pp = _pp()
    bars = [[0, 100, 100, 100, 100, 1], [1, 100, 100.2, 99.0, 99.5, 1], [2, 99.5, 100.5, 99.4, 100.3, 1]]
    r = pp.simulate_v2(bars, 0, "short", 101, [99.1, 98.2], 0.4, 4, 10)
    assert r["bars"] == 1 and abs(r["R"] - (0.4 * 0.225 - 25 * 2 * 6 / 1e4)) < 1e-9


def test_v2_vtoraya_cel_0_9R():
    pp = _pp()
    bars = [[0, 100, 100, 100, 100, 1], [1, 100, 100.0, 99.0, 99.5, 1], [2, 99.5, 99.6, 96.0, 96.5, 1]]
    r = pp.simulate_v2(bars, 0, "short", 101, [99.1, 98.2], 0.4, 4, 10)
    assert abs(r["R"] - (0.4 * 0.225 + 0.6 * 0.9 - 25 * 2 * 6 / 1e4)) < 1e-9
