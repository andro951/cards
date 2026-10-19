# Generation speed investigation — resumed and download queue updated

The user resumed by supplying Diagnostics (12). The earlier pause notes below are historical.

## State
- No code changes were made during this generation-speed investigation.
- Latest available diagnostics: D:/isaac/Downloads/BulkProxyForge_Diagnostics (11).zip. No newer archive was present when checked.
- Requested diagnostics from the current slow run; user asked to pause instead. Do not claim the cause of the current 15-minute run is known.
- Diagnostics (11) recorded Cats: 113 faces, 184.03 seconds total, 177.48 seconds preparation overlapping rendering, 174.57 seconds rendering, 1.82 seconds final commit. Later unchanged Cats runs took about 1.3–1.4 seconds and rendered zero faces.

## Inspected
- foundry/workspace.py prepare_steps: cached preparation checks, streamed GitHub artwork prefetch, generation targets, final preparation checkpoint.
- site/render.js: atomic generation, streamed preparation/rendering, 1–3 rendering workers, concurrent image saves.
- site/native-render-pool.js: bounded render/save pipeline and frame affinity.
- web/workspace-files.js: GitHub artwork downloads in batches of six with a 48 MiB buffer budget.
- web/render-save.js: direct PNG validation/hash/write and grouped final generation metadata.
- No regression was established from source inspection alone.

## Last completed fixes before this pause
- Background Read card details route in foundry/browser.py now wraps resolve_metadata_steps in BrowserStore.batch_import_steps, deferring repeated metadata cache checkpoints while preserving foreground-save durability. 33 scheduling/staged-import/browser-job tests pass; app rebuilt.
- Generation discovers a newly added data.json in the configured GitHub project when no data source was linked previously. Confirmed cats GitHub data has Mirri → Bell, Queen of Sass and Kaheera → Mr. Finntastic. 27 refresh tests pass; app rebuilt.
- Token rules/flavor fitting stops above P/T overlay; 54 token text checks pass; app rebuilt.

## Resume
Obtain the current slow run’s diagnostics and inspect its preparation/render/commit timing breakdown and card counts before choosing any generation optimization. Preserve the many existing uncommitted changes. Do not use the program-audit skill or modify the personal workspace database.

## Diagnostics (12) findings and completed changes
- Completed 134-face generation: 619.43 seconds wall time; preparation 615.27 seconds overlapping rendering, final commit 2.21 seconds. Three artwork-prefetch timeout warnings. A separate earlier run was still incomplete after roughly nine minutes when its job log stopped.
- Batch-of-six artwork downloads waited for every file before publishing results or starting the next group. Changed WorkspaceFiles.prefetch to a bounded six-slot queue that immediately publishes each completed file and starts the next one. It retains the shared 48 MiB buffer budget, immutable cache identities, file validation, and individual failure results.
- Preparation now uses cards whose required artwork has finished while an earlier card waits. It leaves deck card order unchanged and calculates per-card artwork URL plans once, avoiding repeated cache/database scans on every poll.
- Added regression checks for stalled downloads, success/failure/cancellation, incremental publication, concurrency bounds, preparation order and unchanged deck order. 46 download/pipeline/transaction/cache checks pass.
- Rebuilt dist. No full live rerun of the user's 134-face deck was performed, so the new wall-clock duration on their connection is not yet measured.
- Nickname fix confirmed in Diagnostics (12): the Cats run registered two affected faces in 11.99 seconds, with subsequent single-face updates in 7.55 and 9.44 seconds.

## Follow-up implementation after the read-only review

All seven reviewed findings are addressed: browser runtime GETs defer cold network reads to a bounded asynchronous queue; artwork retries remain asynchronous and exhausted failures never fall back to blocking preparation; GitHub freshness checks are scoped to one Generate; token and alternate-art matching use indexes; ordinary token conversions use text-only native seeds and finalize fitting once; generation screens and summary clocks include preflight. Source saves reset freshness scopes.

Combined focused regression suite: 311 passed. Actual static-browser generation/progress checks: 8 passed, including API responsiveness during delayed frame downloads and atomic commit/abort/reload/final-save failure. Offline generation/setup/artwork/token UI checks: 13 passed, plus a new preflight screen/freshness test passed. The additional 126 color/style output comparisons were identical. The final actual-browser cancellation/retry check passed, including an immediate retry after cancellation. The distribution was rebuilt; the latest follow-up/download suite passed 23 checks, including identical assets sharing a writer across independent requests. See docs/PREPARATION_PERFORMANCE.md for design and component benchmark results. No personal workspace database or GitHub data was modified; no full user-deck timing run was performed.
