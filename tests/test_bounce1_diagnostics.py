from bot.diagnostics import _bounce1_no_signal_diag_key


def test_bounce1_no_signal_reasons_are_bounded() -> None:
    expected = {
        "": "bounce1_ns_blank",
        "symbol_not_allowed": "bounce1_ns_symbol",
        "regime_not_bullish": "bounce1_ns_regime",
        "same_signal_bar": "bounce1_ns_same_bar",
        "rsi_invalid_63.4": "bounce1_ns_rsi",
        "no_support_touch": "bounce1_ns_touch",
        "no_reclaim": "bounce1_ns_reclaim",
        "body_weak_0.120": "bounce1_ns_body",
        "ema_extension_2.100": "bounce1_ns_ema",
        "entry_too_far_2.500atr": "bounce1_ns_dist",
        "rr_too_low_0.80": "bounce1_ns_risk",
    }
    assert {reason: _bounce1_no_signal_diag_key(reason) for reason in expected} == expected
