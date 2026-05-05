"""OANDA broker integration for forex/CFD live trading.

Готов к API credentials. Ключи берутся из .env:
  OANDA_API_TOKEN     — API token из OANDA Account Settings
  OANDA_ACCOUNT_ID    — Account ID (typical: 001-001-XXXXXXX-001)
  OANDA_ENV           — practice (paper) | live (real money)
  OANDA_BASE_URL      — auto from OANDA_ENV, override only if needed

Modules:
  client.py — REST API wrapper
  bridge.py — signal → order placement bridge
"""
