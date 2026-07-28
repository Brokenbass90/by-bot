"""Persistent risk-zero decision/fill/exit lifecycle for strategy shadows."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _adverse_fill(raw_price: float, side: str, bps: float, *, entry: bool) -> float:
    direction = 1.0 if side == "long" else -1.0
    if not entry:
        direction *= -1.0
    return float(raw_price) * (1.0 + direction * float(bps) / 10_000.0)


class StrategyShadowLedger:
    """One pending/open virtual position per symbol, with atomic persistence."""

    schema_id = "strategy_risk_zero_shadow_v1"

    def __init__(
        self,
        state_path: Path | str,
        ledger_path: Path | str,
        *,
        strategy: str,
        execution_interval_ms: int = 300_000,
        fee_bps_per_side: float = 6.0,
        slippage_bps_per_side: float = 2.0,
    ):
        self.state_path = Path(state_path)
        self.ledger_path = Path(ledger_path)
        self.strategy = str(strategy)
        self.execution_interval_ms = max(1, int(execution_interval_ms))
        self.fee_bps_per_side = max(0.0, float(fee_bps_per_side))
        self.slippage_bps_per_side = max(0.0, float(slippage_bps_per_side))
        self._state = self._load()

    def _empty(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "strategy": self.strategy,
            "broker_calls": False,
            "mode": "shadow",
            "pending": {},
            "open": {},
            "seen_signal_ids": [],
            "closed_count": 0,
        }

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return self._empty()
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return self._empty()
        if (
            state.get("schema_id") != self.schema_id
            or state.get("strategy") != self.strategy
            or state.get("broker_calls") is not False
        ):
            raise ValueError("incompatible or unsafe shadow state")
        return state

    def snapshot(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._state))

    def _persist(self) -> None:
        _atomic_json(self.state_path, self._state)

    def _event(self, event: str, ts_ms: int, payload: Mapping[str, Any]) -> None:
        _append_jsonl(
            self.ledger_path,
            {
                "schema_id": self.schema_id,
                "event": event,
                "ts_ms": int(ts_ms),
                "strategy": self.strategy,
                "mode": "shadow",
                "broker_calls": False,
                **dict(payload),
            },
        )

    def record_signal(self, signal: Any, *, decision_ts_ms: int) -> bool:
        symbol = str(getattr(signal, "symbol", "") or "").upper()
        side = str(getattr(signal, "side", "") or "").lower()
        entry = float(getattr(signal, "entry", 0.0) or 0.0)
        sl = float(getattr(signal, "sl", 0.0) or 0.0)
        tp = float(getattr(signal, "tp", 0.0) or 0.0)
        tps = [float(value) for value in (getattr(signal, "tps", None) or [tp])]
        fractions = [
            float(value)
            for value in (getattr(signal, "tp_fracs", None) or [1.0 / len(tps)] * len(tps))
        ]
        if not symbol or side not in {"long", "short"}:
            return False
        if symbol in self._state["pending"] or symbol in self._state["open"]:
            return False
        if len(tps) != len(fractions) or not tps or sum(fractions) > 1.000001:
            return False
        if not (entry > 0 and sl > 0 and tp > 0):
            return False

        identity = {
            "strategy": self.strategy,
            "symbol": symbol,
            "side": side,
            "decision_ts_ms": int(decision_ts_ms),
            "entry": entry,
            "sl": sl,
            "tps": tps,
            "tp_fracs": fractions,
        }
        signal_id = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        if signal_id in self._state["seen_signal_ids"]:
            return False

        fill_after_ms = (
            int(decision_ts_ms) // self.execution_interval_ms + 1
        ) * self.execution_interval_ms
        pending = {
            **identity,
            "signal_id": signal_id,
            "fill_after_ms": fill_after_ms,
            "time_stop_bars": max(0, int(getattr(signal, "time_stop_bars", 0) or 0)),
            "reason": str(getattr(signal, "reason", "") or ""),
        }
        self._state["pending"][symbol] = pending
        self._state["seen_signal_ids"] = (
            list(self._state["seen_signal_ids"]) + [signal_id]
        )[-5000:]
        self._persist()
        self._event("decision", decision_ts_ms, pending)
        return True

    def on_price(self, symbol: str, raw_price: float, *, ts_ms: int) -> list[str]:
        symbol = str(symbol or "").upper()
        raw_price = float(raw_price or 0.0)
        ts_ms = int(ts_ms)
        if not symbol or raw_price <= 0 or ts_ms <= 0:
            return []
        events: list[str] = []

        pending = self._state["pending"].get(symbol)
        if pending and ts_ms >= int(pending["fill_after_ms"]):
            side = pending["side"]
            fill = _adverse_fill(
                raw_price,
                side,
                self.slippage_bps_per_side,
                entry=True,
            )
            risk = abs(fill - float(pending["sl"]))
            geometry_ok = (
                risk > 0
                and (
                    (side == "long" and float(pending["sl"]) < fill < min(pending["tps"]))
                    or (side == "short" and float(pending["sl"]) > fill > max(pending["tps"]))
                )
            )
            del self._state["pending"][symbol]
            if geometry_ok:
                opened = {
                    **pending,
                    "fill_ts_ms": ts_ms,
                    "fill_price": fill,
                    "initial_risk": risk,
                    "remaining": 1.0,
                    "realized_return": -self.fee_bps_per_side / 10_000.0,
                    "next_tp_index": 0,
                }
                self._state["open"][symbol] = opened
                self._event("fill", ts_ms, opened)
                events.append("fill")
            else:
                self._event(
                    "cancel",
                    ts_ms,
                    {
                        **pending,
                        "raw_price": raw_price,
                        "reason": "next_open_invalidates_geometry",
                    },
                )
                events.append("cancel")

        trade = self._state["open"].get(symbol)
        if trade:
            events.extend(self._advance_open(symbol, trade, raw_price, ts_ms))

        if events:
            self._persist()
        return events

    def _advance_open(
        self,
        symbol: str,
        trade: dict[str, Any],
        raw_price: float,
        ts_ms: int,
    ) -> list[str]:
        events: list[str] = []
        side = trade["side"]
        sl_hit = raw_price <= float(trade["sl"]) if side == "long" else raw_price >= float(trade["sl"])
        if sl_hit:
            self._close(symbol, trade, raw_price, ts_ms, "stop")
            return ["close:stop"]

        while int(trade["next_tp_index"]) < len(trade["tps"]):
            index = int(trade["next_tp_index"])
            target = float(trade["tps"][index])
            hit = raw_price >= target if side == "long" else raw_price <= target
            if not hit:
                break
            fraction = min(float(trade["remaining"]), float(trade["tp_fracs"][index]))
            exit_fill = _adverse_fill(
                target,
                side,
                self.slippage_bps_per_side,
                entry=False,
            )
            signed_return = (
                (exit_fill / float(trade["fill_price"]) - 1.0)
                * (1.0 if side == "long" else -1.0)
            )
            trade["realized_return"] += fraction * signed_return
            trade["remaining"] = max(0.0, float(trade["remaining"]) - fraction)
            trade["next_tp_index"] = index + 1
            self._event(
                "target",
                ts_ms,
                {
                    "signal_id": trade["signal_id"],
                    "symbol": symbol,
                    "target_index": index,
                    "target": target,
                    "fraction": fraction,
                    "remaining": trade["remaining"],
                },
            )
            events.append(f"target:{index}")
            if trade["remaining"] <= 1e-12:
                self._finalize(symbol, trade, ts_ms, "targets")
                return events + ["close:targets"]

        max_bars = int(trade.get("time_stop_bars", 0) or 0)
        if max_bars > 0:
            expires_ms = int(trade["fill_ts_ms"]) + max_bars * self.execution_interval_ms
            if ts_ms >= expires_ms:
                self._close(symbol, trade, raw_price, ts_ms, "time_stop")
                events.append("close:time_stop")
        return events

    def _close(
        self,
        symbol: str,
        trade: dict[str, Any],
        raw_price: float,
        ts_ms: int,
        reason: str,
    ) -> None:
        fraction = float(trade["remaining"])
        exit_fill = _adverse_fill(
            raw_price,
            trade["side"],
            self.slippage_bps_per_side,
            entry=False,
        )
        signed_return = (
            (exit_fill / float(trade["fill_price"]) - 1.0)
            * (1.0 if trade["side"] == "long" else -1.0)
        )
        trade["realized_return"] += fraction * signed_return
        trade["remaining"] = 0.0
        self._finalize(symbol, trade, ts_ms, reason, exit_fill=exit_fill)

    def _finalize(
        self,
        symbol: str,
        trade: dict[str, Any],
        ts_ms: int,
        reason: str,
        *,
        exit_fill: float | None = None,
    ) -> None:
        trade["realized_return"] -= self.fee_bps_per_side / 10_000.0
        receipt = {
            **trade,
            "close_ts_ms": int(ts_ms),
            "close_reason": reason,
            "exit_fill": exit_fill,
            "net_return": float(trade["realized_return"]),
            "net_r": float(trade["realized_return"])
            * float(trade["fill_price"])
            / max(1e-12, float(trade["initial_risk"])),
        }
        self._event("close", ts_ms, receipt)
        del self._state["open"][symbol]
        self._state["closed_count"] = int(self._state.get("closed_count", 0) or 0) + 1
