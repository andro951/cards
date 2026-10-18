# Render save breakdown — 2026-10-01

## Result

The fixes and new measurements are in [save optimization verification](RENDER_SAVE_VERIFICATION.md#storage-bridge-optimization--2026-10-01). The breakdown below records the behavior before those fixes.

The largest remaining cost is transferring PNG bytes through the synchronous Python/browser filesystem bridge. In a real selected Windows folder, the first unique image took 6.758 seconds. The worker made 119 storage requests taking 6.302 seconds; the corresponding browser filesystem operations took 2.330 seconds. The difference, 3.972 seconds (59% of the whole save), is bridge/transfer overhead rather than time inside the browser filesystem API.

The same 2010x2814 Supernatural render PNG (9,168,781 bytes) was used. Files were physically verified under `D:\isaac\Documents\BulkProxyForge-Save-Benchmark-6e85df8a\profile-5372852b`; byte integrity after app reload passed.

## Ranked stages for the first unique image

These rows subtract nested checkpoints from asset/render stages so they do not double-count time.

| Rank | Action | Seconds | Share |
| --- | --- | ---: | ---: |
| 1 | Create and finalize the render copy | 2.280 | 34% |
| 2 | Write and finalize the content-addressed asset | 2.033 | 30% |
| 3 | Stage incoming bytes in a temporary file and read them into Python | 1.623 | 24% |
| 4 | Persist SQLite metadata snapshots | 0.481 | 7% |
| 5 | Verify and decode PNG pixels | 0.236 | 3.5% |
| 6 | Remaining request/processing overhead | 0.105 | 1.5% |

Raw storage.render (2.542 sec) and storage.asset (2.252 sec) include their respective checkpoint costs. render.persist (5.031 sec) includes validation, asset and render registration, so it must not be added to those rows.

Two subsequent saves of the identical image took 4.415 and 4.392 seconds. They reuse the existing asset, avoiding a new asset write, but still stage the input and make another render copy. A deck's distinct new images generally need the first-write work.

## Why the bridge is expensive

The native PNG already exists in JavaScript. `buffer_bytes()` writes it into the mounted temporary filesystem using Pyodide's safe `to_file()` conversion, then reads it back into Python. Asset ingestion writes those bytes back to browser storage. `render_put()` cannot use os.link on this mounted filesystem, so its fallback copies the asset through Python into a separate render file. The measured render copy has 35 write requests and 37 asset reads. Finally, the browser's rename implementation copies files to their final names before deleting the temporary source.

| Data transfer | Worker request elapsed | Browser write call elapsed |
| --- | ---: | ---: |
| Incoming temporary PNG | 1.220 sec | 0.023 sec |
| Asset PNG | 1.207 sec | 0.028 sec |
| Render PNG, 35 writes combined | 1.283 sec | 0.058 sec |

Closing writers and emulated renames also take appreciable time in the selected folder (roughly 0.28–0.35 seconds per operation in this run). These timings include the browser API and local filesystem effects; this profile does not identify whether antivirus, disk, or another Windows component causes that portion.

Browser storage corroborates the transfer bottleneck: the instrumented first save took 5.017 seconds, with only 0.414 seconds inside browser storage operations. As a control, three direct JavaScript writes of the same PNG to browser storage took 0.040, 0.041 and 0.037 seconds. This control excludes validation, metadata and the full save workflow, and was not measured in the selected Windows folder.

## Recommended next change

Keep large PNG file persistence and copying in the browser filesystem layer. Eliminate the temporary disk round trip for incoming bytes and the asset-to-Python-to-render round trip, while retaining validation, content hashes, durable metadata and atomic failure behavior. Preserve the existing regression protection for Pyodide memory addresses above 2 GiB; replacing the temporary conversion with an unchecked buffer conversion would reintroduce a reproduced correctness issue.

Target the byte-transfer/copy path before further PNG validation or SQLite optimizations. This investigation does not change production persistence behavior.

## Measurement correction and reproduction

The earlier old/new benchmark timed an additional saved-file readback inside its request. Its approximately six-second average was therefore save-plus-verification, not a pure save-request average. This profile omits that readback from each timed save and verifies stored bytes separately afterward. Absolute times differ between runs; use this profile to rank work rather than directly subtracting timings from the earlier benchmark.

`scripts/profile_render_save.py` instruments a temporary built-site copy: existing Python timing scopes, worker synchronous XMLHttpRequest calls, and browser filesystem execute calls. It performs three optimized saves and reload/hash verification. It does not modify vendor or product code. Without arguments it uses an isolated browser workspace and also measures direct JavaScript writes. With an absolute existing benchmark-folder path it reconnects the saved directory handle in the benchmark profile and creates a unique child directory; folder permission may need a user click. Launch it separately on Windows, as with the real-folder benchmark, to keep the browser independent of the tool command lifecycle.

Evidence is in ignored `test-results/save-profile-browser.json` and `test-results/save-profile-selected-folder.json`. Both actual browser workflows and reload verification passed. No unrelated full test sweep was run for this profiling-only change.
