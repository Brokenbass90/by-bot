import json

from bot.geometry_cache import load_cache_rows


def test_load_cache_rows_accepts_list_and_dict_formats(tmp_path) -> None:
    (tmp_path / "BTCUSDT_5_1_2.json").write_text(
        json.dumps([[1000, 1, 2, 0.5, 1.5, 10], [2000, 1.5, 2.5, 1, 2, 20]]),
        encoding="utf-8",
    )
    (tmp_path / "BTCUSDT_5_3_4.json").write_text(
        json.dumps([{"ts": 3000, "o": 2, "h": 3, "l": 1.5, "c": 2.5, "v": 30}]),
        encoding="utf-8",
    )

    rows = load_cache_rows("BTCUSDT", "5", data_cache_dir=tmp_path)

    assert [row[0] for row in rows] == [1000, 2000, 3000]
    assert rows[0][1:] == [1.0, 2.0, 0.5, 1.5, 10.0]
    assert rows[-1][1:] == [2.0, 3.0, 1.5, 2.5, 30.0]
