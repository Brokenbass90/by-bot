#!/usr/bin/env python3
"""Судья тени POLY_SPRAVEDLIVAYA_TEN — тот же poly_yes_verdikt.sudit на журнале data/poly_spravedlivaya_ten.jsonl (до 30 — только счётчики)."""
import poly_yes_verdikt as V
if __name__ == "__main__":
    V.main(V.LAB / "data" / "poly_spravedlivaya_ten.jsonl", "poly_sprav_verdikt_latest", "Polymarket «справедливая цена + хедж» тень")
