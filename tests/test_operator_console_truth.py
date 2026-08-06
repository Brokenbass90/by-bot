from pathlib import Path


OPERATOR_CONSOLE = (
    Path(__file__).resolve().parents[1] / "web" / "static" / "operator_console.html"
)


def _source() -> str:
    return OPERATOR_CONSOLE.read_text(encoding="utf-8")


def _connections_script(source: str) -> str:
    start = source.index("var connEndpointAvailable=false")
    end = source.index("async function loadStrat", start)
    return source[start:end]


def test_connections_have_no_demo_accounts_or_success_fallbacks() -> None:
    source = _source()
    connections = _connections_script(source)

    for fabricated_value in ("bybit-main", "bitget-arb", "••••R4", "••••8f"):
        assert fabricated_value not in source
    assert "getJSON('/api/admin/connections'" not in connections
    assert "{ok:true,latency_ms:120,can_trade:true,can_withdraw:false}" not in connections
    assert "fetchJSON('/api/admin/connections/'+id+'/test',{method:'POST'})" in connections


def test_missing_connections_endpoint_is_fail_closed_and_visible() -> None:
    source = _source()
    connections = _connections_script(source)

    assert "renderConnectionUnavailable()" in connections
    assert "Connections unavailable / not connected" in connections
    assert '<span class="pill warn">unavailable / not connected</span>' in connections
    assert "connEndpointAvailable=false;setConnectionControlsEnabled(false)" in connections

    contract_check = connections.index("if(!d||!Array.isArray(d.rows))")
    enable_controls = connections.index(
        "connEndpointAvailable=true;setConnectionControlsEnabled(true)"
    )
    assert contract_check < enable_controls

    for control_id in ("c-name", "c-exch", "c-scope", "c-key", "c-secret", "c-add"):
        assert f'id="{control_id}"' in source
        control = source[source.index(f'id="{control_id}"') :]
        assert "disabled" in control.split(">", 1)[0]


def test_operator_console_points_to_supported_api_key_navigation() -> None:
    source = _source()

    assert '<a class="btn" href="/">Основная консоль</a>' in source
    assert "Tools → API Keys" in source


def test_main_api_key_ui_requires_apply_proof_and_never_echoes_secrets() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "web" / "static" / "index.html").read_text(encoding="utf-8")
    assert "apply_when_flat" in text
    assert "fresh heartbeat + auth OK" in text
    assert "Withdrawal permission" in text
    assert "ANY IP" in text
