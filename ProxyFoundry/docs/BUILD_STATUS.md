# Current build and verification

Updated 2026-10-01. This replaces the obsolete early integration checkpoint.

The final product is a static website with the engine running in the browser. The local preview launcher serves static files for development and local use; there is no hosted application server.

- Routine pytest gate: 511 passed, 0 failed, 0 skipped in the selected group (189.15 seconds).
- JavaScript syntax and six Node adapter/helper checks passed.
- Actual static Chromium workflow and template validation checks passed.
- Ten browser storage checks passed, including selected-folder reconnection, tab ownership, binary ZIP persistence, interrupted generation, quota recovery, file rename/log rotation, cached file metadata invalidation, immediate deck deletion/order guards/reload recovery, and failed-rename source/destination preservation and retry.
- The 100-image browser session completed and preserved all images after reload (2180.96 seconds); the final bridge passed a separate native render with memory forced above 2 GiB.
- Approved Card Tools files match their canonical Git blobs.

[Testing instructions and individual timings](TESTING.md) describe routine versus affected/full-sweep groups. [Session status](SESSION_STATUS.md) describes the behavior now implemented. This repair run does not imply that every unrelated extended test or a live manufacturing handoff was rerun.