#!/usr/bin/env python3
"""
probe_batch.py — прогон пробы живости по списку стратегий, возобновляемый.

Зачем отдельный раннер: одиночные вызовы с коротким таймаутом дают
ЛОЖНУЮ картину — «нет ответа» смешивает три разные причины:
   TIMEOUT    стратегия просто медленная
   NO_CLASS   другой интерфейс, класса с maybe_signal/evaluate нет
   ERROR      падает
   0 сигналов структурная ошибка ИЛИ редкий сетап
   N сигналов живая
Каждая требует разного действия, поэтому они разделены явно.

Запускать повторно, пока не обработает всех: готовые пропускаются.
    python3 research_lab/probe_batch.py [символ] [баров] [секунд_на_стратегию]
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "research_lab", "results", "liveness_probe.json")
SYM = sys.argv[1] if len(sys.argv) > 1 else "SOLUSDT"
BARS = sys.argv[2] if len(sys.argv) > 2 else "12000"
PER = int(sys.argv[3]) if len(sys.argv) > 3 else 25
BUDGET = 33

GROUPS = {
    "флэт / отскок / пила": [
        "alt_range_scalp_v1", "alt_support_bounce_v1", "alt_support_bounce_v2",
        "range_mean_reversion_v1", "alt_channel_bounce_v1", "alt_range_reclaim_v1",
        "flat_resistance_fade_live", "scalper_bounce_v2", "scalper_classic_v1",
    ],
    "инплей / разгон": [
        "inplay_breakout", "inplay_retest_v3", "inplay_retest_v4",
        "alt_inplay_breakdown_v1", "alt_inplay_breakdown_v2",
        "pump_fade_v2", "pump_momentum_v1",
    ],
    "пробои": [
        "alt_momentum_breakout_v1", "alt_squeeze_breakout_v1",
        "impulse_volume_breakout_v1", "session_open_breakout_v1",
        "scalper_breakout_v2", "micro_scalper_breakout_v1",
    ],
    "ретесты": [
        "breakdown_retest_v3", "sloped_break_retest_v1",
        "event_expansion_retest_long_v1", "btc_regime_retest_v1",
    ],
    "элдер": [
        "elder_crypto_v1", "elder_triple_screen_v2", "elder_triple_screen_v3",
        "alt_elder_revived_v1",
    ],
}

res = json.load(open(OUT)) if os.path.exists(OUT) else {}
t0 = time.time()
todo = [(g, s) for g, ss in GROUPS.items() for s in ss if s not in res]
print(f"осталось: {len(todo)} из {sum(len(v) for v in GROUPS.values())}", flush=True)

for grp, s in todo:
    if time.time() - t0 > BUDGET:
        print("[бюджет] запусти ещё раз — продолжит", flush=True)
        break
    if not os.path.exists(os.path.join(ROOT, "strategies", f"{s}.py")):
        res[s] = dict(group=grp, status="NO_FILE", signals=None)
        continue
    try:
        p = subprocess.run(
            [sys.executable, "research_lab/strategy_liveness_probe.py", s, SYM, BARS],
            cwd=ROOT, capture_output=True, text=True, timeout=PER)
        out = (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        res[s] = dict(group=grp, status="TIMEOUT", signals=None)
        print(f"{s:<32} TIMEOUT", flush=True)
        continue

    sig = None
    for line in out.splitlines():
        if line.startswith("СИГНАЛОВ:"):
            sig = int(line.split(":")[1].strip())
            break
    if sig is not None:
        st = "ЖИВАЯ" if sig > 0 else "НОЛЬ_СИГНАЛОВ"
    elif "не найден класс стратегии" in out:
        st = "ДРУГОЙ_ИНТЕРФЕЙС"
    elif "Traceback" in out or "Error" in out:
        st = "ПАДАЕТ"
    else:
        st = "НЕЯСНО"
    err = ""
    if st in ("ПАДАЕТ", "НЕЯСНО"):
        err = " | ".join(l.strip() for l in out.strip().splitlines()[-2:])[:160]
    res[s] = dict(group=grp, status=st, signals=sig, detail=err)
    print(f"{s:<32} {st:<18} {sig if sig is not None else ''} {err[:60]}", flush=True)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(res, open(OUT, "w"), indent=2, ensure_ascii=False)
done = sum(1 for v in res.values())
print(f"[сохранено] {done} стратегий -> {OUT}", flush=True)
