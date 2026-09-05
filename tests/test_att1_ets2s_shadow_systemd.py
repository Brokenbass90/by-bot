from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_service_is_isolated_public_oneshot_with_root_owned_deployment_anchor() -> None:
    text = (ROOT / "deploy/systemd/att1-ets2s-signal-shadow.service").read_text(encoding="utf-8")
    for required in (
        "Type=oneshot",
        "/usr/bin/python3 /usr/local/libexec/att1-ets2s-shadow-launcher --once",
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
        "ProtectHome=yes",
        "PrivateDevices=yes",
        "CapabilityBoundingSet=CAP_SETUID CAP_SETGID",
        "RestrictAddressFamilies=AF_INET AF_INET6",
        "ReadWritePaths=/opt/bybot-research/att1-ets2s-signal-shadow/app/runtime",
    ):
        assert required in text
    assert "User=bybot-research" not in text
    assert "scripts/run_att1_ets2s_signal_shadow.py" not in text
    assert "scripts/launch_att1_ets2s_shadow.py" not in text
    assert "EnvironmentFile=" not in text
    assert "EXPECTED_CONFIG_SHA256" not in text
    assert "alpaca" not in text.lower()


def test_timer_runs_just_after_each_h1_close_and_is_not_enabled_by_code() -> None:
    text = (ROOT / "deploy/systemd/att1-ets2s-signal-shadow.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* *:02:00" in text
    assert "Persistent=yes" in text
    assert "systemctl enable" not in text
