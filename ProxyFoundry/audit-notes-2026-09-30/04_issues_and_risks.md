# Risks requiring targeted reproduction

## R1 — High: whole-workspace memory growth

web/engine-worker.js:10 mounts the workspace through mountNativeFS and :65 syncs POST mutations. Pyodide's native filesystem mounts MEMFS and reads remote file bytes into memory; synchronization reconciles that copy with persistent storage. See [official filesystem documentation](https://pyodide.org/en/stable/usage/file-system.html) and [upstream implementation](https://github.com/pyodide/pyodide/blob/main/src/js/nativefs.ts).

Consequences: image-heavy libraries, named render outputs, backups and ZIPs can accumulate memory and repeated synchronization work. storage.py's copy fallback may duplicate render bytes when hard links are unavailable. Large binary response copies add transient allocations. The recent response-object leak fix addresses one allocation path, not the storage architecture.

Confirmed architecture; unproven cause of the 80/100 failure. No fixed browser memory ceiling is asserted. Reproduce with multiple real decks, reload, rendering, backup and ZIP, measuring working-set growth and recovery. Prefer direct browser binary storage/streams and bounded per-card scratch space over mounting the full library into Python memory.

## R2 — High: independent tabs may overwrite a shared workspace

Each tab has its own database/filesystem snapshot; no workspace writer lock was found. Per-copy revision checks cannot arbitrate across those snapshots. Synchronization may lose updates. Not reproduced. Introduce a single writer/ownership protocol and test two tabs before claiming multi-tab safety.

## R3 — High: worker and routing recovery remain fragile

Service-worker ownership is transient, startup registration happens once, and controller changes are not re-registered. A fallback owner can become ambiguous with multiple tabs. Request/MessageChannel paths lack a general timeout; browser diagnostics keep only bounded current-session memory. Recent worker error handling is useful, but does not prove recovery from a hung worker or process termination.

Use explicit ownership/version handshake, bounded waits, persistent last-session diagnostics, and durable generation checkpoints. Avoid routing an unknown client's workspace request to an arbitrary tab. Reproduce reload/update/worker interruption mid-generation.

## R4 — Medium: Normal Look conflicts with presets and generation timing

Normal Look resets ordinary template rules, but imported default-preset art/symbol/back settings can remain. Define whether Normal Look always resets those settings. Earlier instructions asked for auto-preparation after choosing Normal; later instructions say no generation before Generate Images. Recommend a consistent explicit generation step, subject to resolving that exception. Do not silently reinterpret the earlier approval.

## R5 — Medium: GitHub Pages project-path deployment not finished

Root-relative site/web/API/service-worker paths assume root hosting. A repository Pages URL under /cards/ needs base-path support unless a root custom domain is chosen. No Pages deployment workflow was found. Test the actual intended hosting path; do not introduce an application server.

## R6 — Medium: tests and documentation overstate production assurance

Many browser/native tests use LocalServer and the threaded Python backend, so they do not exercise BrowserJobs, browser persistence or the production bridge. CI runs the entire enabled pytest suite on every relevant push with a 20-minute timeout rather than the documented routine/extended split. Current stale production assertion blocks later checks. Routine test success alone does not establish browser production reliability.

The browser engine must boot before the current UI becomes usable, and loads runtime dependencies from the network. This adds startup latency and dependency availability to the local baseline's behavior. Documentation claiming generated template previews is also stale after the intentional placeholder change.
