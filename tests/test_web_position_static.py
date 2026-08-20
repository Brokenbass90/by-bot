from pathlib import Path


POSITION_HTML = Path(__file__).resolve().parents[1] / "web" / "static" / "position.html"


def _source() -> str:
    return POSITION_HTML.read_text(encoding="utf-8")


def test_alpaca_fractional_quantity_is_not_formatted_as_an_integer():
    source = _source()

    assert "const fmtQty = x =>" in source
    assert "n.toFixed(9).replace(/\\.?0+$/, \"\")" in source
    assert "${fmtQty(p.qty)}" in source
    assert "fmt(p.qty,0)" not in source
    assert "const num = v => { const n=Number(v);" in source


def test_flat_crypto_view_clears_chart_and_shows_scanning_state():
    source = _source()

    flat_branch = source.index("if(!p){ chartRequestId++; cs.setData([]); clearLines();")
    flat_source = source[flat_branch:flat_branch + 300]
    assert "нет открытых позиций — бот сканирует рынок" in flat_source


def test_symbol_change_resets_chart_and_rejects_stale_responses():
    source = _source()

    assert "const requestId = ++chartRequestId" in source
    assert "requestId!==chartRequestId" in source
    assert "requestId===chartRequestId" in source
    assert "const epochMs = v =>" in source


def test_live_position_chart_supports_zoom_pan_and_reset():
    source = _source()

    assert "const TFS =" in source and '["240","4ч"]' in source
    assert "function moreHistory()" in source
    assert "chart.timeScale().fitContent()" in source
    assert "sloped_lines" in source
    assert 'body:JSON.stringify({messages})' in source


def test_dynamic_html_escapes_signal_reason_and_symbols():
    source = _source()
    assert "const esc = s =>" in source
    assert "${esc(why)}" in source
    assert "${esc(p.symbol)}" in source
