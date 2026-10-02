# Foreground service during imports and exports

The browser engine now yields after GitHub folder reads and individual imported
assets, each packaged FRONT/BACK pair, and each exported original, art crop,
review image or backup asset. The legacy local API drains the same generators
synchronously. No production server or duplicate renderer was introduced.

Imports still return one complete setup patch without saving a deck. Exports
publish only after their archive is complete. Cancellation closes the archive
and removes unfinished output, including cancellation after the final item.
Order publication checks the selected deck revisions again, rejecting edits or
deletions made during packaging. Archive write failures release the job queue.

Immutable source assets stay pinned while an export reads them. Foreground
deletion/replacement may remove their original references, but physical asset
cleanup waits until the final reader releases them. Backup and review ZIPs can
therefore finish from their initial snapshot without locking all workspace edits.
The in-memory pins are bounded by the archive's distinct assets and are released
on success, failure or cancellation. An interrupted browser session can retain
orphan files; it cannot publish an incomplete order.

## Controlled static-engine comparison

The benchmark uses actual service-worker, Pyodide, import and review-export
paths. Only its temporary remote fixture adds 75ms per read. Both variants use
the same production core; the serial control drains all chunks within one turn.
These numbers measure queue blocking, not live GitHub speed or PNG throughput.

| Job | Foreground deck read, serial | Foreground deck read, cooperative |
| --- | ---: | ---: |
| GitHub setup, two trials | 0.960–1.790 s | 0.140–0.142 s |
| Review ZIP, 24 images, two trials | 3.271–3.303 s | 0.216–0.257 s |

Serial reads return after the entire job completes. Cooperative reads return
while the job is running. All trial jobs completed and all cancellation trials
returned cancelled; cancelled review archives were removed. A single network
read, image composition or ZIP entry can still take longer than its boundary.
This does not make synchronous network transport interruptible inside a request.

Reproduce with `scripts/profile_job_families.py`. Raw evidence is in
[job-family-profile.json](job-family-profile.json). The affected static test is
`tests/test_website.py::test_static_github_setup_and_review_export_service_foreground_requests`.
Routine tests in `tests/test_job_families.py` cover all seven routes, archive
bytes, cleanup, final-boundary cancellation, stale order publication, storage
failure and snapshot integrity during deletion.