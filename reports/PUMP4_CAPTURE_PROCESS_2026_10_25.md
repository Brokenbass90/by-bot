# PUMP4 capture/intake process separation —25October2026

**DEPLOYED ORDERS_OFF; actual next-H1 latency PENDING; TINY_NOT_READY.**

Actual17H1 after warm replay/CPU1core:137published/128intakePASS,
10publications≤60s,107sources≤60s; min13.566/median90.8925/max110.562s,
8source failures+HFTunavailable,0signals. This is improvement versus13H1,
not an actual publication gate PASS or controlled cross-hour speed benchmark.
[Actual17H1 evidence](evidence/pump4_warm_publication_20261025/actual-17h-final.json).

Read-only file-time decomposition (proxies, not exact profiling):median47.145s
between source fsync and batch creation;148ms between batch and publication.
Wholecycle59.99CPU seconds,110.56s last publication. Actual CPU1core showed
only.13s throttling by72s; queue/contention remains. Separate GIL is a bounded
engineering hypothesis, not a proven attribution from those proxies alone.

## Selected existing-component change

Existing public capture now runs in one fresh credential-free interpreter.
Existing Supervisor parent holds its original DATA lock and remains sole
intake/journal writer. No second account owner, executor, service or framework.
The child emits bounded strict symbol/hash notices only after source fsync;
parent derives paths, verifies metadata/hour/hash and runs the same intake.
Full137seal/childexit0/allnotices required for capture completion. Early verified
per-symbol receipts remain distinct from later full coverage.

Minimal environment,closedFDs/stdin,selectors for separate stdout/stderr,
1024byte notices/137unique symbols,600s monotonic deadline,64KiBstderr tail/
1MiBerror limit; all failure paths terminate/reap child. Attempt/completion
markers prevent same-hour retry even if child died after writing a full seal.
Immutable early evidence/journal remains; next hour uses existing recovery.
Parent receive/begin/end and childCPU diagnostics never replace market/source or
publication clocks. Frozen intake9e37540b…9702aa/producer/137universe/60s unchanged.

275local/same275VPS exactPASS,108files/48imports/16modules/106fixture receipts,
networkdenied/unshare--net onVPS,0fallback/realbrokerrequests/writes.71targetedPASS.
One new bounded actualastra/high review0Critical/Important; metadata verified.
16real-child cases include parity/earlydurability/no credentials/FD inheritance,
noise/backpressure,malformed/oversize/hash/hour/duplicates,exit/seal/inventory,
silenttimeout and parentloss after fsync. No second independent review claimed.

Material8c00885cf6329bae8cbcaf3d186f8c37c9c980bb82805a3397152355184af079.
DATA candidate8c00885cf6329bae selected17:27:35UTC, binding2f6bbd80…16608.
13159historyfiles preserved; every prior root/scope/claim kept.
ONLY DATA ceiling changed1→2cores on2vCPU host, same768MiB aggregate limit;
quota is a ceiling, not reserved capacity. Actual peak and sibling responsiveness
remain next-H1 checks. Financial policy/budget unchanged.

SAME solefinancialunit/app30677ce6; config1634b014…bd628,scopee6f8c78a…de0cb,
PID2908831/NRestarts0, original818853held. TwofreshGETflat/noordersbarriers,
HEALTHY/NO_NEW_SIGNAL/GOabsent. Monthlyunit9d944…32cc1d unchanged. Cached17archive
through actual new systemd path Result=success/CPUceiling2s; not new-H1 evidence.
Real fresh interpreter with capture disabled also passed(.261s/0requests).

Exact private rollback packet includes copy-forward and known partial wrapper
recovery. Added tested guard: old-code rollback refuses the CURRENT incomplete
process hour; wait next hour/reconcile, because old code does not understand new
attempt markers. No automatic rollback/retry or financial state reset.20same
handoff testsPASS locally/VPS; this conservative addendum root-verified, not an
additional independent signoff. Production rollback not executed.

Next actual18:00UTC H1:137outcomes,source versus parent/durable publication,
childCPU,aggregate memory and original financial-owner continuity. Then fresh
account/cost/lot/oneway/native/source/OFF and exact TINY packet; owner moneyGO absent.
[Evidence](evidence/pump4_capture_process_20261025/).
