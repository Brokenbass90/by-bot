import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rezhim_v1 as R

def _ryad(n=24 * 80, seed=1):
    rng = np.random.default_rng(seed); c = 30000 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    o = np.column_stack([c, c * 1.002, c * 0.998, c, np.ones(n)]); ts = 1672531200000 + np.arange(n) * R.H
    return ts, o

def test_determinizm():
    ts, o = _ryad(); assert R.metki(ts, o) == R.metki(ts, o)

def test_prichinnost_budushchee_ne_menyaet_proshloe():
    ts, o = _ryad(); a = R.metki(ts[:1500], o[:1500]); b = R.metki(ts, o)
    assert a == b[:1500]

def test_progrev_i_sostoyaniya():
    ts, o = _ryad(); s = R.metki(ts, o)
    assert s[0] is None and all(x in R.SOSTOYANIYA for x in s[24 * 11:])

def test_zamok_istorii():
    assert R.proverit()
