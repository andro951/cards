# Native PNG save optimization

## Fix

The native renderer produces a complete PNG. The old persistence path passed that file through ordinary artwork ingestion: decode, convert to RGBA, and compress another PNG in Pyodide before writing it. Native render saves now verify PNG chunk integrity, fully decode pixels to reject corruption, check the expected canvas dimensions and limits, then store the original PNG bytes. Ordinary artwork imports retain their conversion behavior.

Browser metadata checkpoints now compare a SHA-256 digest of the database and any SQLite WAL with the last successfully persisted state. Unchanged database contents skip backup and transfer. Changed metadata, including direct SQLite restore/migration changes, still persists. Failed persistence does not update the digest, so retry remains possible. Image and log files continue to write through the existing browser filesystem.

Fine timing stages now include image.decode, image.encode-png, render.validate-png and render.persist, alongside storage and browser save totals.

## Reproduction

An actual static Chromium/Pyodide benchmark sends the same 2010x2814 Supernatural Syr Gwyn render PNG (9,168,781 bytes) through the previous re-encoding path and the new persistence path twice. It measures engine work and the whole request separately, verifies exact byte preservation, and reloads the browser to check the stored SHA-256. The baseline below was captured before skipping duplicate checkpoints.

| Baseline run | Previous full save | Without recompression |
| --- | ---: | ---: |
| First write | 8.086 sec | 5.260 sec |
| Repeated identical image | 6.799 sec | 3.784 sec |

Mean full-request improvement from avoiding recompression alone was 39%. The benchmark is a small isolated workspace, not a prediction of every user's disk/browser/deck latency. Byte preservation can increase file size compared with recompressing at a different compression level; pixels and renderer-produced bytes remain exact.

## Verification

- Routine tests cover exact saved bytes, render registration, wrong dimensions, truncated/corrupted PNGs, non-PNG rejection, duplicate snapshot suppression, direct SQLite mutations and failed checkpoint retries.
- Actual browser storage tests cover file durability, reload recovery, permission/quota errors, ownership, rename/log rotation, deck deletion guards and the save benchmark.
- The actual native render/review/paired-ZIP workflow is verified separately.
- Approved Card Tools blobs are unchanged. No application server is introduced.

Local benchmark evidence is in ignored test-results/render-save-benchmark-before-checkpoint.json and render-save-benchmark.json.

Final paired benchmark with snapshot suppression enabled: old re-encode path averaged 9.447 seconds; native PNG preservation averaged 5.855 seconds (38.0% faster). These measurements include request transfer and final checkpoint, and were made during the affected regression run; CPU/storage contention affects absolute durations.

Final gates: 528 routine tests passed in 239.30 seconds; all 11 actual browser storage checks passed in 283.56 seconds; native render/review/paired-ZIP workflow passed in 105.64 seconds. The focused validation/checkpoint tests also passed after preserving specific validation error messages.

## Real Windows folder benchmark — 2026-10-01

**Measurement clarification:** these old/new benchmark requests also read the saved PNG back for verification inside the timer. The separate [save profile](RENDER_SAVE_PROFILE.md) times saving without that additional readback and ranks the remaining costs. The figures below remain valid comparisons of the two benchmark paths, but are not pure save latency.

The same four-save Chromium/Pyodide benchmark also passed using a genuine File System Access directory handle selected by the user. This run writes to `D:\isaac\Documents\BulkProxyForge-Save-Benchmark-6e85df8a`, rather than browser storage or an OPFS stand-in for a folder handle. It uses the same 2010x2814 PNG, 9,168,781 bytes, and the same old/new save operations as the browser benchmark.

| Save | Previous full request | Optimized full request |
| --- | ---: | ---: |
| First write | 9.146 sec | 7.198 sec |
| Repeated identical image | 7.229 sec | 4.564 sec |
| Mean | 8.187 sec | 5.881 sec |

The optimized path was **28.2% faster** in this selected-folder run. Engine-only means were 6.361 sec before and 4.089 sec after. These measurements include validation, asset/render persistence and request overhead; they are not isolated disk-write latency. Browser storage's previous optimized mean was 5.855 sec, so the two optimized results were similar here. Separate runs with two samples each do not establish that one storage type is generally faster.

Verification passed for byte preservation, recovery after app reload, physical asset/render files with the expected SHA-256, PNG dimensions, four rendered files, and the physical SQLite metadata snapshot. Evidence is in ignored `test-results/render-save-selected-folder.json`; the browser-storage report is preserved separately.

The reproducible developer harness is `scripts/benchmark_selected_folder.py`, invoked with the absolute parent folder the user will select. It opens a real picker, creates a unique test subfolder, and checks a marker there before running. Launch its Python process separately on Windows (for example, `Start-Process -WindowStyle Hidden`) so the tool command lifecycle does not close its interactive browser. Folder permission remains a user action. The local HTTP server serves the static website only; application work still runs in the browser. This benchmark was the verification for this documentation/harness change; unrelated test suites were not rerun.

## Storage bridge optimization — 2026-10-01

Incoming request bytes now use a temporary memory filesystem file for the safe Pyodide `to_file()` conversion, avoiding a physical/browser-storage staging write. Temporary data is removed even after failure. Large PNG requests keep a request-scoped copy in the browser; when Python writes the exact same bytes as an asset, the filesystem bridge sends a small buffer reference instead of sending the PNG back through synchronous XMLHttpRequest. The comparison normalizes signed byte views and does not reuse altered/re-encoded data. References are removed on success, request error and engine failure.

Render copies now stream directly between browser file handles. They retain the temporary-file/final-rename sequence and commit render metadata only after a successful copy. The local application's hard-link/copy behavior is retained. PNG validation, SHA-256 asset identity, metadata checkpoints and high-address regression protections remain active.

| Pure save request, same 9,168,781-byte PNG | Before | After |
| --- | ---: | ---: |
| Browser storage, first unique image | 5.017 sec | 0.898 sec |
| Browser storage, repeated image, mean | 3.412 sec | 0.616 sec |
| Selected Windows folder, first unique image | 6.758 sec | 2.321 sec |
| Selected Windows folder, repeated image, mean | 4.404 sec | 1.364 sec |

The first unique save is about 82% faster in browser storage and 66% faster in the selected folder in these small runs. The timed save excludes verification readback. Folder results were physically verified in `D:\isaac\Documents\BulkProxyForge-Save-Benchmark-6e85df8a\profile-5372852b\profile-25a4ff22`. Both profiles preserve exact PNG bytes and survive app reload. First-save bridge calls fell from 119 to 28; staging input fell from 1.623 sec to 0.007 sec in the folder run. Absolute timings depend on Windows, storage and concurrent activity.

The folder's remaining work includes native writer close/finalization, emulated renames and metadata snapshots. A direct JavaScript file write control took 0.231–0.244 seconds in that folder. The complete workflow still does more than one write and validates the image, so the control is not a complete-save target or guarantee.

Regression checks cover exact cached input reuse (including signed views), rejection of altered/recompressed bytes from that shortcut, release of request buffers, copy failure with new/existing destinations, successful retry, preserving a prior render and metadata after a partial failed copy, reload recovery, and an actual native render with memory above 2 GiB. The first combined browser run had an interrupted-job recovery test fail; its focused rerun passed, and the final combined run is recorded below. The 100-image stress and unrelated extended suites were not run.

Final gates: 13 actual browser storage tests passed in 266.98 sec; forced above-2-GiB binary/input/native-render verification passed in 77.80 sec; all 531 then-collected routine tests passed in 238.10 sec. The newly added partial-copy unit regression also passed separately (six render-storage unit tests in 5.64 sec), bringing the current routine group to 532. JavaScript syntax checks passed. The focused cache-reuse/reload benchmark was rerun after restricting buffer caching to PNG requests and passed.
