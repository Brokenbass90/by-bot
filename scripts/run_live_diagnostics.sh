#!/usr/bin/env bash
set -euo pipefail

# Live diagnostics helper:
# - pulls bybot journal from server
# - computes delta counters from first/last diag lines
# - prints signal/no-signal and ws reliability ratios

HOST="${BYBOT_SSH_HOST:-root@64.226.73.119}"
KEY="${BYBOT_SSH_KEY:-$HOME/.ssh/by-bot}"
SINCE="${SINCE:-24 hours ago}"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

ssh -i "$KEY" "$HOST" \
  "journalctl -u bybot --since '$SINCE' --no-pager | grep -E 'diag '" > "$TMP" || true

if [[ ! -s "$TMP" ]]; then
  echo "No diag lines found for since='$SINCE'"
  exit 0
fi

python3 - "$TMP" <<'PY'
import re
import sys
from pathlib import Path

p = Path(sys.argv[1])
lines = [x.strip() for x in p.read_text(encoding="utf-8", errors="ignore").splitlines() if "diag " in x]
if not lines:
    print("No diag lines parsed")
    raise SystemExit(0)

KEYS = (
    "ws_connect",
    "ws_disconnect",
    "ws_handshake_timeout",
    "breakout_try",
    "breakout_no_signal",
    "breakout_entry",
    "breakout_skip_liq",
    "breakout_skip_pullback",
    "breakout_skip_quality",
    "breakout_skip_minqty",
    "breakout_ns_no_break",
    "breakout_ns_regime",
    "breakout_ns_retest",
    "breakout_ns_hold",
    "breakout_ns_dist",
    "breakout_ns_impulse",
    "breakout_ns_impulse_weak",
    "breakout_ns_impulse_body",
    "breakout_ns_impulse_vol",
    "breakout_ns_entry_timing",
    "breakout_ns_invalid_risk",
    "breakout_ns_history",
    "breakout_ns_symbol",
    "breakout_ns_stop",
    "breakout_ns_atr",
    "breakout_ns_range",
    "breakout_ns_post",
    "breakout_ns_other",
    "midterm_try",
    "midterm_no_signal",
    "midterm_entry",
    "midterm_skip_minqty",
)

def parse_diag(line: str):
    d = {}
    for k, v in re.findall(r"([a-z_]+)=([0-9]+)", line):
        d[k] = int(v)
    return d

def parse_pid(line: str):
    m = re.search(r"python\[(\d+)\]", line)
    return int(m.group(1)) if m else None

parsed = [parse_diag(x) for x in lines]
pids = [parse_pid(x) for x in lines]
pid_switches = 0
for i in range(1, len(pids)):
    if pids[i] is not None and pids[i - 1] is not None and pids[i] != pids[i - 1]:
        pid_switches += 1

delta = {k: 0 for k in KEYS}
resets = {k: 0 for k in KEYS}

for i in range(1, len(parsed)):
    prev = parsed[i - 1]
    cur = parsed[i]
    for k in KEYS:
        pv = prev.get(k, 0)
        cv = cur.get(k, 0)
        d = cv - pv
        if d >= 0:
            delta[k] += d
        else:
            # Counter reset (bot restart): continue from current absolute value.
            delta[k] += cv
            resets[k] += 1

def r(num, den):
    return (num / den * 100.0) if den > 0 else 0.0

b_try = delta["breakout_try"]
b_no = delta["breakout_no_signal"]
b_ent = delta["breakout_entry"]
b_s_liq = delta["breakout_skip_liq"]
b_s_pb = delta["breakout_skip_pullback"]
b_s_q = delta["breakout_skip_quality"]
b_s_mq = delta["breakout_skip_minqty"]
b_ns_nb = delta["breakout_ns_no_break"]
b_ns_rg = delta["breakout_ns_regime"]
b_ns_rt = delta["breakout_ns_retest"]
b_ns_hd = delta["breakout_ns_hold"]
b_ns_ds = delta["breakout_ns_dist"]
b_ns_im = delta["breakout_ns_impulse"]
b_ns_im_w = delta["breakout_ns_impulse_weak"]
b_ns_im_b = delta["breakout_ns_impulse_body"]
b_ns_im_v = delta["breakout_ns_impulse_vol"]
b_ns_et = delta["breakout_ns_entry_timing"]
b_ns_ir = delta["breakout_ns_invalid_risk"]
b_ns_hs = delta["breakout_ns_history"]
b_ns_sy = delta["breakout_ns_symbol"]
b_ns_st = delta["breakout_ns_stop"]
b_ns_at = delta["breakout_ns_atr"]
b_ns_rg2 = delta["breakout_ns_range"]
b_ns_ps = delta["breakout_ns_post"]
b_ns_ot = delta["breakout_ns_other"]

m_try = delta["midterm_try"]
m_no = delta["midterm_no_signal"]
m_ent = delta["midterm_entry"]
m_s_mq = delta["midterm_skip_minqty"]

ws_c = delta["ws_connect"]
ws_d = delta["ws_disconnect"]
ws_h = delta["ws_handshake_timeout"]

sum_resets = sum(resets.values())

print("=== LIVE DIAG DELTA ===")
print(f"diag_lines={len(lines)} pid_switches={pid_switches} counter_resets={sum_resets}")
print(
    f"breakout: try={b_try} entry={b_ent} no_signal={b_no} "
    f"skip_liq={b_s_liq} skip_pullback={b_s_pb} skip_quality={b_s_q} skip_minqty={b_s_mq}"
)
print(f"midterm:  try={m_try} entry={m_ent} no_signal={m_no} skip_minqty={m_s_mq}")
print(f"ws: connect={ws_c} disconnect={ws_d} handshake_timeout={ws_h}")
print("--- ratios ---")
print(f"breakout entry_rate={r(b_ent, b_try):.2f}% | no_signal_rate={r(b_no, b_try):.2f}%")
print(f"midterm  entry_rate={r(m_ent, m_try):.2f}% | no_signal_rate={r(m_no, m_try):.2f}%")
print(f"ws disconnect/connect={r(ws_d, ws_c):.2f}% | handshake/connect={r(ws_h, ws_c):.2f}%")
if b_no > 0:
    print("--- breakout no_signal breakdown ---")
    print(
        f"no_break={b_ns_nb} ({r(b_ns_nb, b_no):.2f}%) | "
        f"regime={b_ns_rg} ({r(b_ns_rg, b_no):.2f}%) | "
        f"retest={b_ns_rt} ({r(b_ns_rt, b_no):.2f}%) | "
        f"hold={b_ns_hd} ({r(b_ns_hd, b_no):.2f}%) | "
        f"dist={b_ns_ds} ({r(b_ns_ds, b_no):.2f}%) | "
        f"impulse={b_ns_im} ({r(b_ns_im, b_no):.2f}%) | "
        f"impulse_weak={b_ns_im_w} ({r(b_ns_im_w, b_no):.2f}%) | "
        f"impulse_body={b_ns_im_b} ({r(b_ns_im_b, b_no):.2f}%) | "
        f"impulse_vol={b_ns_im_v} ({r(b_ns_im_v, b_no):.2f}%) | "
        f"entry_timing={b_ns_et} ({r(b_ns_et, b_no):.2f}%) | "
        f"invalid_risk={b_ns_ir} ({r(b_ns_ir, b_no):.2f}%) | "
        f"history={b_ns_hs} ({r(b_ns_hs, b_no):.2f}%) | "
        f"symbol={b_ns_sy} ({r(b_ns_sy, b_no):.2f}%) | "
        f"stop={b_ns_st} ({r(b_ns_st, b_no):.2f}%) | "
        f"atr={b_ns_at} ({r(b_ns_at, b_no):.2f}%) | "
        f"range={b_ns_rg2} ({r(b_ns_rg2, b_no):.2f}%) | "
        f"post={b_ns_ps} ({r(b_ns_ps, b_no):.2f}%) | "
        f"other={b_ns_ot} ({r(b_ns_ot, b_no):.2f}%)"
    )

print("--- first diag ---")
print(lines[0])
print("--- last diag ---")
print(lines[-1])
PY
