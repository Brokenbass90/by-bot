from research_lab.att1_negative_phenotypes import _bucket, _exit_path, parse_features


def test_parse_features_and_fixed_buckets() -> None:
    features = parse_features("att1 slope=-1.25%/d rsi=51.2 r2=0.973 g2=descending")
    assert features["slope"] == "-1.25%/d"
    assert features["rsi"] == "51.2"
    assert features["g2"] == "descending"
    assert _bucket(0.95, (1.0, 2.0), ("low", "middle", "high")) == "low"
    assert _bucket(2.0, (1.0, 2.0), ("low", "middle", "high")) == "high"


def test_exit_path_preserves_partial_profit_information() -> None:
    assert _exit_path("setup+SL") == "initial_stop"
    assert _exit_path("setup+TRAIL_SL") == "trail_without_tp1"
    assert _exit_path("setup+TP1+TRAIL_SL") == "tp1_then_runner"
    assert _exit_path("setup+TP1+TP2+TRAIL_SL") == "tp2_or_runner"
