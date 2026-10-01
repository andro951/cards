# Current build and verification

Updated 2026-10-01. This replaces the obsolete early integration checkpoint.

The final product is a static website with the engine running in the browser. The local preview launcher serves static files for development and offline-style local use; there is no hosted application server.

- Routine pytest gate: 502 passed, 0 failed, 0 skipped in the selected group (287.41 seconds).
- JavaScript syntax and six Node adapter/helper checks passed.
- Actual static Chromium workflow and template validation checks passed.
- Seven browser storage checks passed, including selected-folder reconnection, tab ownership, binary ZIP persistence, interrupted generation, quota recovery, file rename/log rotation, and cached file metadata invalidation.
- Approved Card Tools files match their canonical Git blobs.

[Testing instructions and individual timings](TESTING.md) describe routine versus affected/full-sweep groups. [Session status](SESSION_STATUS.md) describes the behavior now implemented. This repair run does not imply that every unrelated extended test or a live manufacturing handoff was rerun.