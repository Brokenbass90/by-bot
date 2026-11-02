# Polymarket WS DATA-only migration — 2 November

Owner approved the next bounded step after the two intake notes: two public WS
feeds + their existing catalogue dependency, resource bounds, recovery and Mac
DATA delivery. No monetary authority/research rule or judge changes. Reuse recovery
checkout; source prototypes are pinned current local drafts, NOT claimed published
research acceptance (canonical origin was30951f9; WS prototypes absent there).

Approach selected by owner: isolate only these light data processes on existing
VPS; do not run old whole-research perenos script or move Ollama/Factory/Brain.
Current research selection reused from pinned poly_monitor_minuty.spisok (150cap),
CLOB time-window membership reused from pinned tekushchie. Original sources copied
unchanged into candidate inputs; no edits to Claude checkout/code. Preserve full
raw WS frames, local receive wall/monotonic clocks, source payload clocks separately,
connection IDs/gaps and post-fsync segment seals. Both outcome tokens are captured
as data coverage, never a new selection/strategy or executable opposite price.

Services: catalogue oneshot30min, sports and CLOB, one dynamic unprivileged user,
credential paths inaccessible; fixed public URLs/send allowlist, no broker libs.
CPU total≤30%oneCPU (10%each), memory≤128MiB each/catalog192MiB, tasks≤32,
Nice15/idleIO; Pythonstdlib+isolated public websockets vendor, no global pip.
Disk budgets sports128MiB/CLOB512MiB/catalog128MiB, free disk floor2GiB. No automatic
research evidence deletion: cap=>visible STOP/exit78, no silent dropping. Export
closed gzip segments+hash seals, leave crash partials intact. Raw duplicates retained;
absence of venue sequence means external completeness UNKNOWN, never blanketPASS.

Cutover: stage/test/independentreview first, then stop only exact Mac sportsws/clobws
processes after argv/path/lock identity proof; block their existing launcher by
chmod0400 only these two DATA lock files, preservinginode/prior mode. It survives
sleep/reboot for normal launcher; a deliberate direct Python bypass is outside
this selector. No financial lock or other collector touched. Mac oldlogs retained.
VPS starts only after local refusal proven. Failure=>stop only newunits and restore
these modes; never repeat financial commands. Record handoff gap; no backdating.

Mac receives create-exclusive immutable sealed artifacts into a separate
research_lab/data/poly_ws_vps_v1 dataset. No appending/replacing old research logs;
no judge/outcomes run. Existing native Mac launchd runs pinned pull periodically,
AI not required; Macsleepcatchup preservesactualimporttime. Claude consumes this
new source version explicitly; old judges are not silently repointed.

Acceptance: exactsourcepins, resources+isolation, soleproducer proof, actualnew
sports/CLOB/subscription frames or explicitWAIT_NO_ACTIVE_MARKETS, disconnect/
restart distinctgap preservingsegments, samefiles idempotentMacimport and unchanged
PUMP4/Monthly/DATA/LIQunits+scope/lock. No profitability or executablewindowclaim.
