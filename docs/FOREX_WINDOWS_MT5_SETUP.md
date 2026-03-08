## Windows MT5 Demo Sidecar

Why:
- Real MT5 Python execution is effectively Windows-only.
- This macOS/Linux workspace can backtest and dry-run, but cannot place MT5 demo orders directly.

What you need:
- Windows VPS or Windows PC
- Installed `MetaTrader 5`
- Logged-in `FxPro` demo account inside MT5
- Python 3.11+ on that Windows machine

Morning checklist:
1. Get a Windows VPS or use an always-on Windows PC.
2. Install `MetaTrader 5`.
3. Log into your `FxPro` demo account in MT5.
4. Install Python and copy this repo there.
5. Create local file `configs/forex_mt5_demo_local.env`.
6. Put:
   - `MT5_LOGIN=...`
   - `MT5_PASSWORD=...`
   - `MT5_SERVER="FxPro-MT5 Demo"`
   - `FOREX_BRIDGE_SEND_ORDERS=0`
7. In project venv run:
   - `pip install MetaTrader5`
8. Start dry-run:
   - `bash scripts/run_forex_mt5_demo_bridge.sh`
9. If MT5 initializes cleanly and logs look normal:
   - set `FOREX_BRIDGE_SEND_ORDERS=1`
   - run the same script again

Notes:
- This is for `demo` only.
- Current Forex strategies are for forward validation, not real deployment.
