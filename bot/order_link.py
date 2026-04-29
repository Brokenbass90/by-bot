"""Order link ID + idempotency helpers — выделено из smart_pump_reversal_bot.py.

Чистый модуль, не зависящий от websockets/requests/etc. Тестируется отдельно.

Использование:
    from bot.order_link import make_order_link_id, log_order_link

    link_id = make_order_link_id("main", "BTCUSDT", "Buy", intent="open")
    body["orderLinkId"] = link_id
    j = client.post("/v5/order/create", body)
    oid = j["result"]["orderId"]
    log_order_link("main", link_id, oid, body, status="placed")

См. PATCH_TIER1_orderLinkId_RETRY_20260429.md в корне репо.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Optional


# 5m bar bucket — внутри одного бара (300 секунд) одинаковые входы дают
# одинаковый orderLinkId. После смены бара ID становится другим.
BAR_BUCKET_SEC = 300

# Bybit лимит orderLinkId = 36 символов. SHA1[:28] = 112 бит коллизионной
# устойчивости — заведомо больше, чем нужно.
LINK_ID_LEN = 28


def make_order_link_id(
    client_name: str,
    symbol: str,
    side: str,
    intent: str = "open",
    *,
    now_ts: Optional[float] = None,
) -> str:
    """Детерминированный per-bar orderLinkId.

    Аргументы:
        client_name : имя BybitClient (например "main")
        symbol      : "BTCUSDT"
        side        : "Buy" или "Sell"
        intent      : "open" | "open_quote" | "close" — разделяет open и close
                      на одном баре, чтобы они не коллизировали.
        now_ts      : опциональный override времени для тестов.

    Возвращает:
        28-символьный hex-строка SHA1.
    """
    ts = time.time() if now_ts is None else now_ts
    bar_ts = int(ts // BAR_BUCKET_SEC) * BAR_BUCKET_SEC
    raw = f"{client_name}|{symbol}|{side}|{intent}|{bar_ts}"
    return hashlib.sha1(raw.encode()).hexdigest()[:LINK_ID_LEN]


def log_order_link(
    client_name: str,
    link_id: str,
    order_id: str,
    body: dict,
    status: str,
    *,
    log_path: Optional[Path] = None,
    error_logger=None,
) -> None:
    """Append-only лог linkId → orderId для post-mortem диагностики.

    status ∈ {"placed", "duplicate_recovered", "failed"}.
    Никогда не бросает исключений — если запись падает, ошибку только логируем.
    """
    if log_path is None:
        # Default: caller должен передать path или предварительно установить;
        # без явного path в этой функции пишем в /tmp как fallback.
        log_path = Path("/tmp/order_link_id_log.jsonl")
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": int(time.time()),
            "client": client_name,
            "link_id": link_id,
            "order_id": order_id or "",
            "symbol": (body or {}).get("symbol", ""),
            "side": (body or {}).get("side", ""),
            "qty": (body or {}).get("qty", ""),
            "reduce_only": bool((body or {}).get("reduceOnly", False)),
            "status": status,
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        if error_logger is not None:
            try:
                error_logger(f"order_link_id_log write fail: {e}")
            except Exception:
                pass
