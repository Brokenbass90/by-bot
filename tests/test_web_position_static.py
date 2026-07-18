from pathlib import Path


POSITION_HTML = Path(__file__).resolve().parents[1] / "web" / "static" / "position.html"


def _source() -> str:
    return POSITION_HTML.read_text(encoding="utf-8")


def test_alpaca_fractional_quantity_is_not_formatted_as_an_integer():
    source = _source()

    assert "const fmtQty = x =>" in source
    assert "n.toFixed(9).replace(/\\.?0+$/, \"\")" in source
    assert "${fmtQty(p.qty)} шт" in source
    assert "fmt(p.qty,0)" not in source


def test_flat_crypto_view_clears_chart_and_shows_scanning_state():
    source = _source()

    flat_branch = source.index("if (!v.positions || !v.positions.length)")
    populated_branch = source.index("} else {", flat_branch)
    flat_source = source[flat_branch:populated_branch]

    assert "Открытых позиций нет" in flat_source
    assert "Бот сканирует рынок." in flat_source
    assert 'resetChart("Открытой криптопозиции нет — бот сканирует рынок.")' in flat_source
    assert "ctx.clearRect(0, 0, cv.width, cv.height)" in source


def test_symbol_change_resets_chart_and_rejects_stale_responses():
    source = _source()

    symbol_reset = source.index("if (symbol !== chartSymbol)")
    throttle = source.index("if (now - chartLoaded < 60000) return")

    assert symbol_reset < throttle
    assert "resetChart(`Загрузка графика ${symbol}…`, symbol)" in source
    assert "const requestId = ++chartRequestId" in source
    assert source.count("requestId !== chartRequestId || symbol !== chartSymbol") == 2
