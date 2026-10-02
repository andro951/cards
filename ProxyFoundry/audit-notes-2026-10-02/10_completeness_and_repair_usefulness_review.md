# Audit usefulness and limits

This package maps the relevant execution/storage surfaces and records source
entry points, measured failures, repairs and regression checks. Chunk results
and verification commands are in 09_recheck_log.md and the linked docs.

Measured work includes worker scheduling, scoped foreground ownership, collection
input retention, render/save overlap on both storage types, native yields,
cooperative GitHub/archive work, renderer concurrency and worker compatibility,
small previews, startup stages and repeated artwork normalization. Synthetic
queue/DOM timings and isolated warm-operation gains are not end-to-end deck
speed claims. Exact pixels, native PNG bytes and reload checks remain gates.

The expanded 400-output run exposed real Python memory exhaustion after 36
images. Controlled worker reads isolated WAL opens as the growth trigger.
Rollback journaling repairs the browser case: 4,000-read regression and a
complete 400-output save/reload pass with bounded memory. Original failure
evidence is retained. The strengthened import-during-generation run and final
all-enabled verification remain open.
The earlier isolated startup timeout also has no established cause, despite
24 successful profiling launches and subsequent successful static flows.

The 400-output fixture repeats four public-deck printings with distinct face IDs.
It exercises output count, persistence and foreground input during generation;
it does not represent 400 distinct artworks. Structural native cases separately
cover differing layouts. Remaining risks and acceptance gaps are explicit in
04_issues_and_risks.md and 08_requirements_checklist.md.