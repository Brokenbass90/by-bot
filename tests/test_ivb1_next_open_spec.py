from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ivb1_recheck_is_targeted_and_uses_next_open() -> None:
    spec = json.loads(
        (ROOT / "configs" / "autoresearch" / "ivb1_short_next_open_recheck_v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert "--entry-on-next-open" in spec["command"]
    assert spec["base_env"]["IVB1_DIRECTION_MODE"] == "short"
    combos = 1
    for values in spec["grid"].values():
        combos *= len(values)
    assert combos == 8
