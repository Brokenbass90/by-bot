# ETS2M pre-due input check — October 6

**ARMED_PROCESS_ALIVE /PRE_DUE_BLOCKED_COHORT_PIN_MISMATCH.**
Local one-shot PID46460 remains alive with original command/manifest/runtime,
startOctober5 22:35local. Due **October10 19:00UTC /22:00Cyprus** unchanged.
This is a source-check failure, not a strategy verdict or early judge run.

Authorized `--check` returns `ValueError: COHORT_PIN_MISMATCH`. All five original
code/config/epoch source pins still match. The first900 entries sorted by(ts,sym)
now hash **35f7b2a87679656dd3a7cef487e1a6b9a92a8286cef475ffd5cced2587f97c7b**;
original manifest hash is
**0bcea9a398bac4af4509406a1e3ea5d67cafddd5d757935460422eb7c448a718**.
Current source1570 entries, selected900; last signal1790290800000 equals the
original cutoff. Same count/cutoff does not prove same cohort bytes. Underlying
change/backfill/mutation cause NOT_PROVEN; original manifest stores the cohort
hash, count and cutoff, not a complete first900 archive.

No outcome file was opened; frozen evaluator was not executed early. No source,
manifest, rule, waiting job or sealed cohort was edited. No job restart, due-date
change, re-arm or silent repinning. The original waiting process can still write
an honest BLOCKED_DATA terminal at due if this mismatch persists; its liveness
must not be reported as readiness to judge a valid unchanged sample.

One bounded recovery also checked the first1461 raw/unique entry prefix (the
previous launch inventory), using the same frozen sort/canonicalization. No
duplicate entry IDs exist in the1570 current rows. Both prefix attempts hash
5ed1804a0653f390f785320987f8460dc7c704d19aed3b6df882c0b038fc8828,
which does not recover the original pin. No pre-arm cohort archive exists in the
waiting-job runtime (only schedule/lock/log). This is not proof of a particular
mutation/backfill cause. Do not keep trying convenient alternative samples.

Next bounded task: recover **exact original900 entry bytes/identity** from existing
source-bound pre-arm archives and establish the source-only difference. If not
recoverable, return BLOCKED_DATA rather than select another convenient900 or
invent original evidence. A reviewed recovery must preserve original frozen
judge/cohort/due constraints. Mac must remain powered/awake for the existing job.
No Claude checkout write or message was made.

Private receipt `.private/owner_close_20261006/ets2m_predue_check.json`.
Reproduction, input pins only:

```sh
.venv/bin/python -B scripts/ets2m_unattended_verdict.py \
  --manifest reports/ETS2M_UNATTENDED_MANIFEST_2026_10_05.json \
  --runtime .private/ets2m_verdict_20261010 --check
```

Run without `--check` only after the fixed due gate; do not inspect outcomes now.
