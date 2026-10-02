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
