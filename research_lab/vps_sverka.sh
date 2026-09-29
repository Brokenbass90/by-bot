#!/bin/bash
# vps_sverka.sh — совпало ли состояние на VPS с эталоном Mac. ТОЛЬКО ЧТЕНИЕ.
# Запускать НА VPS после перевозки и ДО запуска служб.
# Код возврата: 0 — PASS, 1 — FAIL.
set -uo pipefail
KOREN="$(cd "$(dirname "$0")/.." && pwd)"; cd "$KOREN"
exec python3 research_lab/vps_sravnit.py --rezhim do
