# PUMP4 current-hour source repair implementation plan

> **For agentic workers:** Use superpowers:executing-plans for this bounded repair.

**Goal:** Remove the growing archive from current-entry discovery without deleting
history, loosening causal admission, changing frozen strategy or expanding LIVE.

**Architecture:** Keep legacy source selection unchanged for old configs. A new
explicit config value candidate_source=CURRENT_H1_PUBLICATIONS_V1 selects the
existing ws-hours/<hour>/published index (max137), cross-checks each publication
against its immutable observation, then reuses original eligibility, causal H1
replay, account admission, cooldown and deduplication. No new producer/framework.
The updated config/source envelope requires independent acceptance before selection.

**Tech stack:** Existing Python TrustedSources, source binding, safe file reader,
current stream publications, pytest, existing selected owner and exact scope pins.

- [x] RED: reproduce archive>20000, current signal available, no archive scan/write.
- [x] Add minimal opt-in path in pump4_runtime_sources_v1.py; fail closed on changed
  publication/observation, wrong hour/symbol, invalid times/mode/hash or symlinks.
  No late/backfilled signal becomes new. Outside entry window no candidate work.
- [x] Targeted legacy/runtime/source/supervisor regression; independent critical
  review once. Stage isolated candidate, no current LIVE file/unit/policy changes.
- [x] Real read-only source replay at its actual capture clock is diagnostic only;
  it cannot claim a missed trade or a fresh/live opportunity.
- [x] Record exact unchanged financial caps/expiry, remaining source-envelope GO /
  physical handoff requirements and current Monthly selection. Never extend GO,
  reset journal/claims, rotate API keys or restart a financial owner automatically.

Chosen over raising archive cap (same eventual failure) or deleting evidence.
Owner already requests finishing existing work without more design rounds. This
is an execution-source repair, not a new strategy or automatic financial GO.

Result:196local/same196VPS and actualpublicparserreplay PASS; no LIVE selection.
NEXT exactfinancialrepair envelope/GO/handoff before deployment. APIvalid6Nov but
7daycustody mayoutliveit; existing1Noventryexpiry unchanged. Full report in
reports/PUMP4_SOURCE_BOUND_REPAIR_2026_11_01.md.
