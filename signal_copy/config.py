# -*- coding: utf-8 -*-
"""Настройки signal_copy.

Всё, что касается денег, задаётся здесь, а не в коде. Любое значение можно
переопределить переменной окружения — удобно, чтобы не править файл.
"""
import os


def _flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "да")


def _ints(name: str, default: tuple[int, ...]) -> tuple[int, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    out = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return tuple(out)


# ── связь с терминалом ───────────────────────────────────────────────────
MT5_URL   = os.getenv("SIGCOPY_MT5_URL", "http://127.0.0.1:22346/mcp")
MT5_TOKEN = os.getenv("SIGCOPY_MT5_TOKEN", "")

# ── главный рубильник ────────────────────────────────────────────────────
# 0 — бот разбирает сигналы и считает лот, но ордера не отправляет вообще.
EXECUTION_ENABLE = _flag("SIGCOPY_EXECUTION_ENABLE", "0")

# ── риск ─────────────────────────────────────────────────────────────────
RISK_PCT      = float(os.getenv("SIGCOPY_RISK_PCT", "0.5"))    # % от средств на сделку
MAX_RISK_PCT  = float(os.getenv("SIGCOPY_MAX_RISK_PCT", "2.0"))  # выше — отказ
MAX_LOT       = float(os.getenv("SIGCOPY_MAX_LOT", "0.50"))
MAX_POSITIONS = int(os.getenv("SIGCOPY_MAX_POSITIONS", "3"))
DEFAULT_TP    = int(os.getenv("SIGCOPY_DEFAULT_TP", "4"))       # какую цель канала брать, 1..4

# ── свежесть сигнала ─────────────────────────────────────────────────────
# Сигнал живёт минуты. Пока его вставляют, рынок уезжает, и сделка перестаёт
# быть той, которую описал канал.
MAX_ENTRY_DRIFT_R = float(os.getenv("SIGCOPY_MAX_DRIFT_R", "0.5"))
MIN_RR            = float(os.getenv("SIGCOPY_MIN_RR", "0.5"))
MIN_STOP_SPREADS  = float(os.getenv("SIGCOPY_MIN_STOP_SPREADS", "8"))
MIN_RISK_KEEP     = float(os.getenv("SIGCOPY_MIN_RISK_KEEP", "0.35"))

# ── ИИ ───────────────────────────────────────────────────────────────────
# По умолчанию всё крутится локально в Ollama: бесплатно и ничего не уходит
# наружу. DeepSeek включается отдельно и осознанно — одного ключа в .env мало.
ALLOW_REMOTE_LLM = _flag("SIGCOPY_ALLOW_REMOTE_LLM", "0")

# ── куда вообще можно торговать ──────────────────────────────────────────
# Три независимых замка: сервер, конкретный номер счёта и тип счёта.
# Подключил не тот терминал — ордер не уйдёт.
ALLOWED_SERVERS        = tuple(s.strip() for s in os.getenv(
    "SIGCOPY_ALLOWED_SERVERS", "MetaQuotes-Demo").split(",") if s.strip())
ALLOWED_ACCOUNT_LOGINS = _ints("SIGCOPY_ALLOWED_ACCOUNT_LOGINS", ())
ALLOWED_ACCOUNT_TYPES  = tuple(s.strip().lower() for s in os.getenv(
    "SIGCOPY_ALLOWED_ACCOUNT_TYPES", "demo").split(",") if s.strip())
ALLOW_LIVE             = False
