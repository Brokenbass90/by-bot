from research_lab.validator import validate


RETURNS = [0.010, -0.002] * 50
PHASES = [
    [0.010, -0.002] * 18,
    [0.009, -0.002] * 18,
    [0.008, -0.002] * 18,
]


def _meta(**overrides):
    value = {
        "windows_overlap": False,
        "posthoc_thresholds": False,
        "universe_includes_delisted": True,
        "taker_bps": 5.5,
    }
    value.update(overrides)
    return value


def test_research_stage_allows_known_evidence_gaps_as_warnings():
    report = validate(
        RETURNS,
        meta=_meta(
            universe_includes_delisted=False,
            posthoc_thresholds="inherited maturity threshold",
        ),
        phases=PHASES,
    )

    assert report.stage == "research"
    assert report.ok
    assert "[WARN]" in report.text()


def test_capital_stage_blocks_missing_pit_oos_slippage_and_execution_parity():
    report = validate(
        RETURNS,
        meta=_meta(
            promotion_stage="capital",
            universe_includes_delisted=False,
            posthoc_thresholds="inherited maturity threshold",
        ),
        phases=PHASES,
    )

    assert not report.ok
    failed = {check.name for check in report.checks if not check.passed}
    assert {
        "пороги пре-регистрированы",
        "универсум с делистингами",
        "независимый OOS",
        "проскальзывание",
        "execution parity",
    }.issubset(failed)


def test_capital_stage_passes_when_all_required_evidence_is_present():
    report = validate(
        RETURNS,
        meta=_meta(
            promotion_stage="capital",
            out_of_sample=True,
            slippage_modelled=True,
            execution_parity=True,
        ),
        phases=PHASES,
    )

    assert report.ok
    assert "ГОДЕН к capital" in report.text()
