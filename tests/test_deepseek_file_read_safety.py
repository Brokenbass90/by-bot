from bot import deepseek_autoresearch_agent as agent


def test_ai_code_refuses_all_config_paths_before_reading() -> None:
    result = agent.read_any_bot_file("configs/alpaca_live_v38.env")

    assert result.startswith("❌ Отказано")


def test_ai_code_still_allows_source_files() -> None:
    result = agent.read_any_bot_file("bot/ai_context.py", max_lines=3)

    assert not result.startswith("❌")
    assert result.strip()
