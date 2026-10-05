# Alpaca DAY re-arm evidence — 2026-10-05

Operational verdict: `REARM_AND_EXIT_LIFECYCLE_PASS` from the supplied local snapshot and postcheck receipts. The checks are mechanical and read-only. They do not claim a continuous cron PID, guaranteed net result, or guaranteed stop loss bound.

The original 58-file source manifest is unchanged: `source_manifest_sha256=73345c03fa823d82a2c330902624206d14123ed6269667774569ec5db1f0fbb2`, with `hashes_match=true` in both receipts. The private binding remains the same account, with capital cap `487.42` USD and gross exposure `0.70`.

The receipt records exactly one NEW manager cron and zero OLD manager cron/process entries. CRWD remains protected at full quantity `0.469970151` by DAY stop `242.13`, order `fde30ddb-c1b6-4e76-8b5d-42cb6cd5eeb5`. META remains protected at full quantity `0.141939508` by DAY stop `668.76`, order `8a7e85f7-c361-4c42-90a9-96c8e2ed5480`. The prior DAY stops are recorded as expired, and active floor/HWM state is asserted monotonic against the prior receipt.

AMD’s full quantity `0.186377282` DAY stop filled at `622.312` against entry `609.57`, producing gross Decimal profit `2.374819327244`. The monthly re-entry block is recorded through `2026-10-26T13:30:31Z`.

Published activities are complete through the fixed cutoff `2026-10-05T13:35:53Z`. The `CAT` fee is `-0.01` and is explicitly aggregated across three entry trades, so it cannot be allocated to AMD. Final net remains `NET_FINALITY_PENDING`.

Next gate: October 6 re-arm at `13:30 UTC` (`16:30 Cyprus`), with fee followup and existing software trailing. No GTC or paper queue changes are recorded.

Reproduce the assertions with:

```sh
python3 .private/alpaca_rearm_20261005/accept.py
```

Expected output: `ACCEPT PASS checks=83 verdict=REARM_AND_EXIT_LIFECYCLE_PASS`.

The 83 offline assertions also bind both snapshots to exact remaining broker positions, unique stop orders, original AMD entry and its broker FILL activities, and completed manager output. They verify the matched gross lifecycle without inferring delayed fee finality.

DAY protection was not queued before the session: CRWD/META stop creation and submission were11.565424/12.139317seconds after13:30UTC. AMD stop creation was10.949724seconds after opening; its broker submitted_at is31.694124seconds after opening, just before fill, so exact initial acceptance timing is not inferred from created_at. Continuous protection from the opening instant remains NOT_PROVEN. Queued next-session fractional DAY-stop PAPER acceptance remains the separate bounded improvement; existing LIVE behavior is unchanged.
