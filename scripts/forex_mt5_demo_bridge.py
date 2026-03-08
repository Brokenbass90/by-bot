#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.data import load_m5_csv
from forex.types import Candle, Signal
from scripts.run_forex_multi_strategy_gate import _build_strategy

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:
    mt5 = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_env_file(path: Path) -> Dict[str, str]:
    env_map: Dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f"env file not found: {path}")
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_map[key.strip()] = value.strip()
    return env_map


def _csv_items(raw: str) -> List[str]:
    return [x.strip() for x in str(raw or "").split(",") if x.strip()]


def _to_float(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value or "")
    except Exception:
        return default


def _parse_combo(raw: str) -> Tuple[str, str]:
    if "@" not in raw:
        raise ValueError(f"bad combo format: {raw}")
    pair, strategy_name = raw.split("@", 1)
    return pair.strip().upper(), strategy_name.strip()


def _default_pip_size(pair: str) -> float:
    return 0.01 if pair.upper().endswith("JPY") else 0.0001


def _signal_key(combo_id: str, candle_ts: int, signal: Signal) -> str:
    return (
        f"{combo_id}|{candle_ts}|{signal.side}|"
        f"{signal.entry:.6f}|{signal.sl:.6f}|{signal.tp:.6f}"
    )


@dataclass
class ComboSignal:
    combo_id: str
    pair: str
    strategy_name: str
    role: str
    risk_pct: float
    candle_ts: int
    signal: Signal
    signal_key: str


class BridgeState:
    def __init__(self, path: Path):
        self.path = path
        self.seen_signal_keys: List[str] = []
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.seen_signal_keys = [str(x) for x in raw.get("seen_signal_keys", []) if x]
            except Exception:
                self.seen_signal_keys = []

    def seen(self, key: str) -> bool:
        return key in set(self.seen_signal_keys)

    def add(self, key: str, keep_last: int) -> None:
        self.seen_signal_keys.append(key)
        if keep_last > 0:
            self.seen_signal_keys = self.seen_signal_keys[-keep_last:]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": _utc_now_iso(),
            "seen_signal_keys": self.seen_signal_keys,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _latest_signal(
    *,
    candles: List[Candle],
    strategy_name: str,
    session_start: int,
    session_end: int,
    max_age_bars: int,
) -> Optional[Tuple[int, Signal]]:
    strategy = _build_strategy(
        strategy_name,
        session_start=session_start,
        session_end=session_end,
    )
    latest: Optional[Tuple[int, Signal]] = None
    for i in range(len(candles)):
        sig = strategy.maybe_signal(candles, i)
        if sig is not None:
            latest = (i, sig)
    if latest is None:
        return None
    idx, sig = latest
    age_bars = (len(candles) - 1) - idx
    if age_bars > max_age_bars:
        return None
    return candles[idx].ts, sig


def _collect_signals(
    *,
    env_map: Dict[str, str],
    data_dir: Path,
    session_start: int,
    session_end: int,
    max_age_bars: int,
    max_bars: int,
) -> List[ComboSignal]:
    active_combos = _csv_items(env_map.get("FOREX_ACTIVE_COMBOS", ""))
    canary_combos = _csv_items(env_map.get("FOREX_CANARY_COMBOS", ""))
    base_risk_pct = _to_float(env_map.get("FOREX_RISK_PER_TRADE_PCT"), 0.5)
    canary_mult = _to_float(env_map.get("FOREX_CANARY_RISK_MULT"), 0.5)

    out: List[ComboSignal] = []
    for role, combos, risk_mult in (
        ("ACTIVE", active_combos, 1.0),
        ("CANARY", canary_combos, canary_mult),
    ):
        for combo_id in combos:
            pair, strategy_name = _parse_combo(combo_id)
            csv_path = data_dir / f"{pair}_M5.csv"
            if not csv_path.exists():
                continue
            candles = load_m5_csv(str(csv_path))
            if max_bars > 0 and len(candles) > max_bars:
                candles = candles[-max_bars:]
            if not candles:
                continue
            latest = _latest_signal(
                candles=candles,
                strategy_name=strategy_name,
                session_start=session_start,
                session_end=session_end,
                max_age_bars=max_age_bars,
            )
            if latest is None:
                continue
            candle_ts, signal = latest
            out.append(
                ComboSignal(
                    combo_id=combo_id,
                    pair=pair,
                    strategy_name=strategy_name,
                    role=role,
                    risk_pct=base_risk_pct * risk_mult,
                    candle_ts=candle_ts,
                    signal=signal,
                    signal_key=_signal_key(combo_id, candle_ts, signal),
                )
            )
    return out


def _normalize_volume(value: float, *, min_volume: float, max_volume: float, step: float) -> float:
    if step <= 0:
        step = 0.01
    clipped = min(max_volume, max(min_volume, value))
    steps = round(clipped / step)
    volume = steps * step
    volume = max(min_volume, min(max_volume, volume))
    decimals = 0
    step_text = f"{step:.8f}".rstrip("0")
    if "." in step_text:
        decimals = len(step_text.split(".", 1)[1])
    return round(volume, decimals)


def _mt5_account_equity() -> Optional[float]:
    if mt5 is None:
        return None
    info = mt5.account_info()
    if info is None:
        return None
    return float(getattr(info, "equity", 0.0) or 0.0)


def _estimate_volume_mt5(signal_row: ComboSignal) -> Tuple[Optional[float], str]:
    if mt5 is None:
        return None, "mt5_module_missing"
    info = mt5.symbol_info(signal_row.pair)
    tick = mt5.symbol_info_tick(signal_row.pair)
    equity = _mt5_account_equity()
    if info is None or tick is None or not equity:
        return None, "mt5_symbol_or_equity_missing"

    price = float(tick.ask if signal_row.signal.side == "long" else tick.bid)
    order_type = mt5.ORDER_TYPE_BUY if signal_row.signal.side == "long" else mt5.ORDER_TYPE_SELL
    one_lot_pnl = mt5.order_calc_profit(order_type, signal_row.pair, 1.0, price, float(signal_row.signal.sl))
    if one_lot_pnl is None:
        return None, "mt5_order_calc_profit_failed"
    loss_per_lot = abs(float(one_lot_pnl))
    if loss_per_lot <= 0:
        return None, "zero_loss_per_lot"

    risk_cash = equity * (float(signal_row.risk_pct) / 100.0)
    raw_volume = risk_cash / loss_per_lot
    volume = _normalize_volume(
        raw_volume,
        min_volume=float(getattr(info, "volume_min", 0.01) or 0.01),
        max_volume=float(getattr(info, "volume_max", raw_volume) or raw_volume),
        step=float(getattr(info, "volume_step", 0.01) or 0.01),
    )
    if volume <= 0:
        return None, "volume_not_positive"
    return volume, "ok"


def _build_order_request(signal_row: ComboSignal, volume: float, deviation: int, magic: int) -> Tuple[Optional[dict], str]:
    if mt5 is None:
        return None, "mt5_module_missing"
    info = mt5.symbol_info(signal_row.pair)
    tick = mt5.symbol_info_tick(signal_row.pair)
    if info is None or tick is None:
        return None, "mt5_symbol_or_tick_missing"
    if not bool(getattr(info, "visible", True)):
        mt5.symbol_select(signal_row.pair, True)
    order_type = mt5.ORDER_TYPE_BUY if signal_row.signal.side == "long" else mt5.ORDER_TYPE_SELL
    price = float(tick.ask if signal_row.signal.side == "long" else tick.bid)
    filling_mode = getattr(info, "filling_mode", mt5.ORDER_FILLING_IOC)
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": signal_row.pair,
        "volume": float(volume),
        "type": order_type,
        "price": price,
        "sl": float(signal_row.signal.sl),
        "tp": float(signal_row.signal.tp),
        "deviation": int(deviation),
        "magic": int(magic),
        "comment": signal_row.combo_id[:31],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }
    return request, "ok"


def _positions_for_pair(pair: str) -> List[object]:
    if mt5 is None:
        return []
    positions = mt5.positions_get(symbol=pair)
    return list(positions or [])


def _mt5_initialize_from_env() -> Tuple[bool, str]:
    if mt5 is None:
        return False, "mt5_module_missing"
    login_raw = os.getenv("MT5_LOGIN", "").strip()
    password = os.getenv("MT5_PASSWORD", "").strip()
    server = os.getenv("MT5_SERVER", "").strip()
    terminal_path = os.getenv("MT5_TERMINAL_PATH", "").strip()
    kwargs = {}
    if terminal_path:
        kwargs["path"] = terminal_path
    if login_raw:
        kwargs["login"] = int(login_raw)
    if password:
        kwargs["password"] = password
    if server:
        kwargs["server"] = server
    ok = mt5.initialize(**kwargs)
    if not ok:
        return False, f"mt5_initialize_failed:{mt5.last_error()}"
    return True, "ok"


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _tg_send(text: str) -> None:
    token = (os.getenv("TG_TOKEN", "") or "").strip()
    chat = (os.getenv("TG_CHAT", "") or "").strip()
    if not token or not chat or not text:
        return
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat, "text": text}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Forex MT5 demo bridge for approved ACTIVE/CANARY combos.")
    ap.add_argument("--env-file", default="docs/forex_demo_env_latest.env")
    ap.add_argument("--data-dir", default="data_cache/forex")
    ap.add_argument("--state-path", default="state/forex_mt5_demo_bridge_state.json")
    ap.add_argument("--log-path", default="runtime/forex_mt5_demo_bridge_latest.jsonl")
    ap.add_argument("--session-start-utc", type=int, default=6)
    ap.add_argument("--session-end-utc", type=int, default=20)
    ap.add_argument("--max-signal-age-bars", type=int, default=1)
    ap.add_argument("--max-bars", type=int, default=5000)
    ap.add_argument("--max-open-per-pair", type=int, default=1)
    ap.add_argument("--dedupe-keep-last", type=int, default=500)
    ap.add_argument("--mt5-deviation-points", type=int, default=20)
    ap.add_argument("--mt5-magic", type=int, default=260308)
    ap.add_argument("--send-orders", action="store_true", help="Actually send orders to MT5 instead of dry-run logging.")
    args = ap.parse_args()

    env_path = (ROOT / args.env_file).resolve()
    data_dir = (ROOT / args.data_dir).resolve()
    state_path = (ROOT / args.state_path).resolve()
    log_path = (ROOT / args.log_path).resolve()

    env_map = _load_env_file(env_path)
    state = BridgeState(state_path)
    rows = _collect_signals(
        env_map=env_map,
        data_dir=data_dir,
        session_start=int(args.session_start_utc),
        session_end=int(args.session_end_utc),
        max_age_bars=max(0, int(args.max_signal_age_bars)),
        max_bars=max(0, int(args.max_bars)),
    )

    mt5_ready = False
    mt5_status = "dry_run"
    if args.send_orders:
        mt5_ready, mt5_status = _mt5_initialize_from_env()

    summary = {
        "checked_at": _utc_now_iso(),
        "env_file": str(env_path),
        "data_dir": str(data_dir),
        "send_orders": bool(args.send_orders),
        "mt5_status": mt5_status,
        "signals_found": len(rows),
        "signals_sent": 0,
        "signals_skipped": 0,
    }

    for row in rows:
        payload = {
            "ts": _utc_now_iso(),
            "combo_id": row.combo_id,
            "pair": row.pair,
            "role": row.role,
            "risk_pct": round(float(row.risk_pct), 4),
            "candle_ts": int(row.candle_ts),
            "signal": asdict(row.signal),
            "signal_key": row.signal_key,
            "mode": "send" if args.send_orders else "dry_run",
        }
        if state.seen(row.signal_key):
            payload["status"] = "skip_duplicate_signal"
            summary["signals_skipped"] += 1
            _append_jsonl(log_path, payload)
            continue

        if args.send_orders and not mt5_ready:
            payload["status"] = "skip_mt5_not_ready"
            summary["signals_skipped"] += 1
            _append_jsonl(log_path, payload)
            _tg_send(f"FX bridge skip {row.pair} {row.signal.side}: mt5_not_ready ({mt5_status})")
            continue

        open_positions = _positions_for_pair(row.pair) if args.send_orders else []
        if args.send_orders and len(open_positions) >= int(args.max_open_per_pair):
            payload["status"] = "skip_open_position_limit"
            payload["open_positions"] = len(open_positions)
            summary["signals_skipped"] += 1
            _append_jsonl(log_path, payload)
            _tg_send(f"FX bridge skip {row.pair} {row.signal.side}: open_limit={len(open_positions)}")
            continue

        volume = None
        volume_status = "dry_run"
        if args.send_orders:
            volume, volume_status = _estimate_volume_mt5(row)
            payload["volume_status"] = volume_status
            payload["volume"] = volume
            if volume is None or volume <= 0:
                payload["status"] = "skip_volume_error"
                summary["signals_skipped"] += 1
                _append_jsonl(log_path, payload)
                _tg_send(f"FX bridge skip {row.pair} {row.signal.side}: volume_error={volume_status}")
                continue
        else:
            payload["volume"] = None
            payload["volume_status"] = volume_status

        if args.send_orders:
            request, request_status = _build_order_request(
                row,
                volume=float(volume),
                deviation=int(args.mt5_deviation_points),
                magic=int(args.mt5_magic),
            )
            payload["request_status"] = request_status
            payload["request"] = request
            if request is None:
                payload["status"] = "skip_request_error"
                summary["signals_skipped"] += 1
                _append_jsonl(log_path, payload)
                _tg_send(f"FX bridge skip {row.pair} {row.signal.side}: request_error={request_status}")
                continue
            result = mt5.order_send(request)
            payload["result"] = result._asdict() if hasattr(result, "_asdict") else str(result)
            retcode = int(getattr(result, "retcode", 0) or 0)
            if retcode == getattr(mt5, "TRADE_RETCODE_DONE", 0):
                payload["status"] = "sent"
                summary["signals_sent"] += 1
                state.add(row.signal_key, keep_last=int(args.dedupe_keep_last))
                _tg_send(
                    f"FX sent {row.role} {row.pair} {row.signal.side}\n"
                    f"combo={row.combo_id}\nvolume={float(volume):.2f} mt5={mt5_status}"
                )
            else:
                payload["status"] = "send_failed"
                summary["signals_skipped"] += 1
                _tg_send(
                    f"FX send_failed {row.role} {row.pair} {row.signal.side}\n"
                    f"combo={row.combo_id}\nretcode={retcode} mt5={mt5_status}"
                )
        else:
            payload["status"] = "dry_run_signal"
            summary["signals_sent"] += 1
            state.add(row.signal_key, keep_last=int(args.dedupe_keep_last))
            _tg_send(
                f"FX dry-run {row.role} {row.pair} {row.signal.side}\n"
                f"combo={row.combo_id}\nentry={row.signal.entry:.5f} sl={row.signal.sl:.5f} tp={row.signal.tp:.5f}"
            )

        _append_jsonl(log_path, payload)

    state.save()
    if args.send_orders and mt5 is not None:
        mt5.shutdown()

    _tg_send(
        f"FX bridge summary\nsend_orders={int(bool(args.send_orders))} mt5={mt5_status}\n"
        f"signals={summary['signals_found']} sent={summary['signals_sent']} skipped={summary['signals_skipped']}"
    )

    print(json.dumps(summary, ensure_ascii=True))
    print(f"log={log_path}")
    print(f"state={state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
