from scripts.run_six_day_research_pipeline import terminal_stage


def test_terminal_stage_requires_every_case_and_no_failures() -> None:
    assert terminal_stage(completed_cases=48, expected_cases=48, failed_cases=[]) == "complete"
    assert (
        terminal_stage(completed_cases=40, expected_cases=48, failed_cases=["one"])
        == "incomplete_case_failures"
    )


def test_terminal_stage_rejects_independently_invalid_cases() -> None:
    assert (
        terminal_stage(
            completed_cases=48,
            expected_cases=48,
            failed_cases=[],
            invalid_cases=["replication:att1:base"],
        )
        == "incomplete_validation_failures"
    )
    assert (
        terminal_stage(completed_cases=47, expected_cases=48, failed_cases=[])
        == "incomplete_case_failures"
    )
