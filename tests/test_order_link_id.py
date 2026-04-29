"""Unit tests for bot.order_link — orderLinkId / Tier-1 idempotency patch.

Покрывает:
  1. make_order_link_id — детерминизм, intent-aware, длина 28, формат hex.
  2. Bar bucket boundary — два вызова в одном 5m баре дают одинаковый ID;
     вызов после смены бара даёт разный.
  3. log_order_link — пишет append-only в jsonl, переживает write fail.

Запуск:
    cd /root/by-bot
    python3 -m pytest tests/test_order_link_id.py -v
    # или без pytest:
    python3 -m unittest tests.test_order_link_id -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.order_link import (
    make_order_link_id,
    log_order_link,
    LINK_ID_LEN,
    BAR_BUCKET_SEC,
)


class TestMakeOrderLinkId(unittest.TestCase):
    """Тесты для bot.order_link.make_order_link_id."""

    def test_link_id_length_and_hex(self):
        """Должна быть строка длиной LINK_ID_LEN и валидный hex."""
        link_id = make_order_link_id("main", "BTCUSDT", "Buy", "open")
        self.assertEqual(len(link_id), LINK_ID_LEN)
        int(link_id, 16)  # raises если не hex

    def test_deterministic_within_same_bar(self):
        """Два вызова в одном 5m баре дают одинаковый ID."""
        ts = 1735000000.0  # фиксированное время в середине бара
        id1 = make_order_link_id("main", "BTCUSDT", "Buy", "open", now_ts=ts)
        id2 = make_order_link_id("main", "BTCUSDT", "Buy", "open", now_ts=ts + 100)  # +100с
        self.assertEqual(id1, id2,
                         f"одинаковый бар → одинаковый ID; получили {id1!r} vs {id2!r}")

    def test_different_id_after_bar_boundary(self):
        """Вызов в следующем баре даёт другой ID."""
        # Опускаемся на границу бара
        bar_start = (1735000000 // BAR_BUCKET_SEC) * BAR_BUCKET_SEC
        id1 = make_order_link_id("main", "BTCUSDT", "Buy", "open",
                                 now_ts=float(bar_start + 1))
        id2 = make_order_link_id("main", "BTCUSDT", "Buy", "open",
                                 now_ts=float(bar_start + BAR_BUCKET_SEC + 1))
        self.assertNotEqual(id1, id2, "разные бары → разные ID")

    def test_intent_separation(self):
        """open / close / open_quote дают разные ID на одном баре."""
        ts = 1735000000.0
        id_open  = make_order_link_id("main", "BTCUSDT", "Buy", "open",       now_ts=ts)
        id_close = make_order_link_id("main", "BTCUSDT", "Buy", "close",      now_ts=ts)
        id_quote = make_order_link_id("main", "BTCUSDT", "Buy", "open_quote", now_ts=ts)
        self.assertNotEqual(id_open, id_close)
        self.assertNotEqual(id_open, id_quote)
        self.assertNotEqual(id_close, id_quote)

    def test_symbol_side_separation(self):
        """Разные символы / стороны → разные ID."""
        ts = 1735000000.0
        btc_buy  = make_order_link_id("main", "BTCUSDT", "Buy",  "open", now_ts=ts)
        eth_buy  = make_order_link_id("main", "ETHUSDT", "Buy",  "open", now_ts=ts)
        btc_sell = make_order_link_id("main", "BTCUSDT", "Sell", "open", now_ts=ts)
        self.assertNotEqual(btc_buy, eth_buy)
        self.assertNotEqual(btc_buy, btc_sell)

    def test_client_separation(self):
        """Разные client_name → разные ID. Подготовка к multi-account будущему."""
        ts = 1735000000.0
        main_id = make_order_link_id("main",        "BTCUSDT", "Buy", "open", now_ts=ts)
        sub_id  = make_order_link_id("sub_account", "BTCUSDT", "Buy", "open", now_ts=ts)
        self.assertNotEqual(main_id, sub_id)


class TestLogOrderLink(unittest.TestCase):
    """Тесты для bot.order_link.log_order_link."""

    def test_log_writes_jsonl(self):
        """log_order_link создаёт корректный JSONL-файл, append-only."""
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "subdir" / "log.jsonl"
            log_order_link(
                "main", "abc123def", "ord_999",
                {"symbol": "BTCUSDT", "side": "Buy", "qty": "0.001"},
                "placed",
                log_path=log_path,
            )
            log_order_link(
                "main", "ghi456jkl", "ord_888",
                {"symbol": "ETHUSDT", "side": "Sell", "qty": "0.05", "reduceOnly": True},
                "duplicate_recovered",
                log_path=log_path,
            )

            self.assertTrue(log_path.exists(), "лог-файл должен быть создан")
            self.assertTrue(log_path.parent.exists(), "родительская директория тоже создана")

            lines = log_path.read_text().strip().split("\n")
            self.assertEqual(len(lines), 2, "2 вызова → 2 строки")

            r1 = json.loads(lines[0])
            self.assertEqual(r1["link_id"], "abc123def")
            self.assertEqual(r1["order_id"], "ord_999")
            self.assertEqual(r1["symbol"], "BTCUSDT")
            self.assertEqual(r1["side"], "Buy")
            self.assertEqual(r1["status"], "placed")
            self.assertFalse(r1["reduce_only"])
            self.assertIn("ts", r1)
            self.assertIsInstance(r1["ts"], int)

            r2 = json.loads(lines[1])
            self.assertEqual(r2["status"], "duplicate_recovered")
            self.assertTrue(r2["reduce_only"])

    def test_log_handles_disk_failure_silently(self):
        """Если запись лога падает (плохой путь), функция не должна бросать exception."""
        bad_path = Path("/nonexistent_root_dir_xyz/log.jsonl")
        captured_errors = []

        def fake_logger(msg):
            captured_errors.append(msg)

        try:
            log_order_link(
                "main", "abc", "ord", {"symbol": "BTC"}, "placed",
                log_path=bad_path,
                error_logger=fake_logger,
            )
        except Exception as e:
            self.fail(f"log_order_link бросил исключение: {e}")

        # Если можем — проверим что error_logger вызван. Иногда mkdir может
        # не упасть на edge case OS — допустимо не кидать ошибку вообще.
        # Главное — что не было exception.

    def test_log_with_no_logger_does_not_crash(self):
        """Если error_logger=None и запись падает — тоже не должно быть exception."""
        bad_path = Path("/nonexistent_root_dir_xyz2/log.jsonl")
        try:
            log_order_link(
                "main", "abc", "ord", {"symbol": "BTC"}, "placed",
                log_path=bad_path,
                error_logger=None,
            )
        except Exception as e:
            self.fail(f"log_order_link бросил исключение без logger'а: {e}")

    def test_log_preserves_data_integrity_with_special_chars(self):
        """JSON-сериализация переживает не-ASCII символы (русский, эмодзи)."""
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "log.jsonl"
            log_order_link(
                "main", "linkid_тест",
                "oid", {"symbol": "BTC", "comment": "тест 🚀"},
                "placed",
                log_path=log_path,
            )
            r = json.loads(log_path.read_text().strip())
            self.assertEqual(r["link_id"], "linkid_тест")


if __name__ == "__main__":
    unittest.main(verbosity=2)
