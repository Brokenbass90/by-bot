# ATT1 local observation candidate and 48-hour research probes

Owner approved the prior diagnosis/fix proposal and two narrow probes, October4.
Native continuation in current codex/recovery-20260824 checkout; foreign allowlist
untouched. No new strategy research, money authority, live transport/policy changes.

- [ ] Local timing candidate: consume each adjacent-pair future when ready; drain
  all outstanding observation futures before an exit IOC, preserving priority.
  Compare received continuity with immutable returnedrx; keep consumed CTS2s.
  For continuous run only, prime at most two eligible adjacent held books before
  publication tail; no refill while management/exit is running, no skipped books,
  buffer overwrite or worker journal writes. Pin exactreturnedrx in timing rows.
  RED/GREEN tests: ETC2399-vs1680, true2442gap, slowpeer barrier/exit safety,
  overlapping publish tail, retained2000/2001CTS and old receipt oracle.
- [ ] Passive transport probe: SEI/SUI RESTbook50 every2s/symbol alongside public
  WSbook50/publicTrade. Preserve originalCTS (missing meansUNKNOWN), ts/u/seq,
  receive/use clocks, rawpayload hashes, reconnect/sequence diagnostics. Max48h,
  4GiB gzip evidence, min5GiB free, stop without deleting data. No key/env access.
  Freeze quiet/stale transport interpretation; quiet WS is not proof of freshness.
- [ ] Funding shadow: baseline existingSTART journals at launch; only later START
  intents are prospective. Exact draftR0.4/N100 sizing with frozen geometry, no
  qty upward rounding. Compare current43-limit reserve with fixed5x historical
  worst43-adverse reserve, notional sensitivity1.0/1.1/1.5, two captured takerfees,
  unresolved liabilities0/0.4 and stress exit-gap0.4. Candidate status always
  RESEARCH_ONLY/NOT_MONEY_READY; changing-notional/liquidation/finality remain
  unproven, dated fees labelled. DailyD0.8 scenarios not an installed cap or ledger.
  Immutable studyhash/draft parameters; no candidate result affects admission.
- [ ] Cash-finality design: separate economiccutoff/receive/reconciled clocks;
  late-event identity/idempotence/reserve holds; do not change actual validator.
- [ ] Appropriate local/full-suite checks, one bounded critical review, four-gap
  replay first. Launch only isolated research services with no credentials,
  absolute deadline persisted across restart, CPU/memory/disk limits, rollback
  receipt and meaningful event-driven followup. No public driver deployment.
- [ ] Final actual-packet readiness delta, canonical handoff, commit/push/remote.

Study verdicts: transportMEASURED orBLOCKED_SOURCE, never bypass2s. Funding
candidate produces per-signal feasibility sensitivities, not profit/edge or GO.
48hours is a maximum collection period; caps/errors explicitly terminate early.
