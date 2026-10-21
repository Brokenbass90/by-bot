"""Регрессии DEV-исправлений 21.10.2026 по ревью Brain (BRAIN_REVIEW_PROVERKA_2026_10_21.md)."""
import math, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "research_lab" / "factory_v3"))
import bot.market_context as mc
from bot.regime_hmm import regime_probs, regime_gate, RegimeState
from bot.adaptive_context import adaptive_params
from bot.elder_filter import elder_bias
from bot.range_filter import range_state


def _row(i, o, h, l, c, v=100.0):
    return [i * 3_600_000, float(o), float(h), float(l), float(c), float(v)]


def _rastushchee_soprotivlenie():
    # бары 0..3: высокие закрытия ДО появления линии (убывающие максимумы — пивотов нет);
    # дальше растущие пивоты 20, 21, 22 и закрытия под линией
    rows = [_row(0, 40, 40, 34, 35), _row(1, 38, 38, 33, 34), _row(2, 36, 36, 32, 33), _row(3, 34, 34, 31, 32)]
    highs = [18, 20, 17, 21, 18, 22, 19, 19.5]
    for k, h in enumerate(highs):
        rows.append(_row(4 + k, h - 2, h, h - 4, h - 3))
    return rows


def test_sloped_level_ne_lomaetsya_barami_do_pervogo_pivota():
    sl = mc.sloped_level(_rastushchee_soprotivlenie(), side="resistance", left=1, right=1, min_pivots=2)
    assert sl is not None and sl["slope"] > 0
    assert sl["valid"] is True          # до 21.10 было False: проверка шла с бара 0


def test_sloped_level_probitaya_posle_formirovaniya_ostaetsya_invalid():
    rows = _rastushchee_soprotivlenie() + [_row(12, 23, 30, 22, 29)]
    sl = mc.sloped_level(rows, side="resistance", left=1, right=1, min_pivots=2)
    assert sl is not None and sl["valid"] is False


def test_regime_hmm_nan_atr_ne_daet_rezhim():
    rows = [[i * 3600000, 100.0, float("nan"), float("nan"), 100.0, 1.0] for i in range(80)]
    st = regime_probs(rows)
    assert st.ok is False and st.dominant == "unknown"


def test_regime_gate_bez_rezhima_ne_daet_novyy_risk():
    st = RegimeState(False, {"bull": .25, "bear": .25, "range": .25, "high_vol": .25}, "unknown", 0.0,
                     float("nan"), float("nan"), "insufficient_data")
    g = regime_gate(st)
    assert g["allow"] is False and g["risk_scalar"] == 0.0


def test_adaptive_params_volatilnost_vazhnee_flata_i_nan():
    assert adaptive_params(8.0, "flat")["tol_atr"] == 0.55
    assert adaptive_params(float("nan"), "flat")["max_age_bars"] == 30
    assert adaptive_params(1.0, "flat")["tol_atr"] == 0.30


def _ryad(n, shag):
    return [_row(i, 100 + i * shag, 101 + i * shag, 99 + i * shag, 100.5 + i * shag, 100 + (i % 7)) for i in range(n)]


def test_elder_bez_istorii_ema200_ok_false():
    b = elder_bias(_ryad(120, 0.5))
    assert b.ok is False and b.reason == "insufficient_data_for_slow_ema"


def test_elder_trend_vverh_pri_polnoy_istorii():
    b = elder_bias(_ryad(260, 0.5))
    assert b.ok is True and b.tide == "up" and b.allow_long and not b.allow_short
    assert "wave_agrees" in b.extra


def test_range_filter_razdelyaet_flat_i_kanal():
    rs = range_state(_ryad(120, 0.0))
    assert "is_flat_range" in rs.extra and "is_sloped_channel" in rs.extra and "degraded" in rs.extra
    assert not (rs.extra["is_flat_range"] and rs.extra["is_sloped_channel"])


def test_zhurnal_korrekciya_ishoda_append_only():
    import opportunity_v2 as V2
    d = Path(tempfile.mkdtemp()); h = V2.Hranilishche(d)
    v = V2.vozmozhnost(source_ref="t", source_sha256="0" * 64, t_observation_ms=1, t_available_ms=2, t_decision_ms=2,
                       sleeve="T", mechanism="M", version="v", symbol="BTCUSDT", side=1, horizon_ms=10, context={}, features={},
                       exp_gross_bps=1.0, cost_fee_bps=0.0, cost_spread_bps=0.0, cost_slip_bps=0.0, cost_funding_bps=0.0,
                       uncertainty_bps=1.0, prior_ref="p", prior_status="s")
    h.dobavit_vozmozhnost(v, t_recorded_ms=3)
    h.prikrepit_ishod(v["opp_id"], 20, 10.0, "src", "1" * 64, t_recorded_ms=21)
    try:
        h.ispravit_ishod(v["opp_id"], 5.0, "", "src", "2" * 64); assert False, "без причины нельзя"
    except V2.OshibkaV2:
        pass
    z = h.ispravit_ishod(v["opp_id"], 5.0, "оценщик считал в неверных единицах", "src2", "2" * 64, t_recorded_ms=30)
    assert z["corrects"] == h.ishody[v["opp_id"]]["record_hash"]
    assert h.ishody[v["opp_id"]]["realized_net_bps"] == 10.0          # оригинал не тронут
    assert h.ishod_aktualnyy(v["opp_id"])["realized_net_bps"] == 5.0
    h2 = V2.Hranilishche(d)                                           # цепочка цела после перезагрузки
    assert h2.ishod_aktualnyy(v["opp_id"])["realized_net_bps"] == 5.0


def test_sloped_level_po_poslednim_pivotam():
    rows = _rastushchee_soprotivlenie()
    sl = mc.sloped_level(rows, side="resistance", left=1, right=1, min_pivots=2, last_pivots=2)
    assert sl is not None and sl["pivots"] == 2 and sl["slope"] > 0


def test_naklonnaya_prichinnost_replay_po_odnomu_baru():
    """Replay по одному закрытому бару: каждая точка линии подтверждена (pivot + right баров) к моменту построения,
    а решение, выданное на баре t, не меняется после появления следующих баров."""
    import random
    random.seed(20261021)
    rows, p = [], 100.0
    for i in range(300):
        p *= 1 + random.uniform(-0.01, 0.0105)
        rows.append(_row(i, p, p * (1 + random.uniform(0, 0.01)), p * (1 - random.uniform(0, 0.01)), p * (1 + random.uniform(-0.005, 0.005))))
    left = right = 2
    resheniya = {}
    for t in range(60, len(rows)):
        okno = rows[t - 59:t + 1]
        piv = mc.pivot_highs(okno, left, right)
        assert all(x["idx"] <= len(okno) - 1 - right for x in piv)            # точка подтверждена right барами
        sl = mc.sloped_level(okno, side="resistance", left=left, right=right, min_pivots=2, last_pivots=3)
        resheniya[t] = None if sl is None else (round(sl["level_now"], 10), sl["valid"])
    for t in range(60, len(rows), 37):                                       # пересчёт с тем же срезом даёт то же решение
        okno = rows[t - 59:t + 1]
        sl = mc.sloped_level(okno, side="resistance", left=left, right=right, min_pivots=2, last_pivots=3)
        assert resheniya[t] == (None if sl is None else (round(sl["level_now"], 10), sl["valid"]))
