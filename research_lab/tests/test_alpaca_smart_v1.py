"""Тесты Smart Selection V1 (d1fab6e): признаки и статистика на синтетике; тождество подмены оценки."""
import math, sys
from datetime import date, timedelta
sys.path.insert(0, ".")
import numpy as np
from backtest.alpaca_exact_parity_contract import DailyBar
import research_lab.alpaca_smart_v1 as S


def ryad(ceny, d0=date(2020, 1, 1)):
    return [DailyBar(session_date=d0 + timedelta(days=i), open=c, high=c * 1.01, low=c * 0.99, close=c) for i, c in enumerate(ceny)]


def test_beta_i_ostatok():
    rng = np.random.default_rng(1); m = rng.normal(0, 0.01, 120)
    spy = ryad(list(100 * np.cumprod(1 + m)))
    a = ryad(list(50 * np.cumprod(1 + 2 * m)))          # бета 2, без своего движения
    assert abs(S.beta60(a, spy) - 2) < 1e-6
    assert abs(S.resid28(a, spy) - (S.mom28(a) - 2 * S.spy_mom28(a, spy))) < 1e-12


def test_beta_malo_par():
    spy = ryad([100.0] * 30); a = ryad([10.0] * 30)
    assert S.beta60(a, spy) == 1.0


def test_nw_i_spearman():
    x = np.ones(50) * 0.1 + np.r_[0.01, -0.01] .repeat(25)
    assert S.nw_t(x, 1) > 0
    assert abs(S.spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1) < 1e-12
    assert abs(S.spearman([1, 2, 3, 4], [4, 3, 2, 1]) + 1) < 1e-12


def test_podmena_bez_izmeneniy():
    b = ryad([100 + i * 0.5 - (3 if i > 75 else 0) for i in range(90)])
    S.CTX["ruka"] = "ID"
    assert S.cand_patch("X", b) == S.ORIG_CAND("X", b)
    S.CTX["ruka"] = "BASE"
