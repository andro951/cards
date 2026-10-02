# Browser database memory

The expanded 400-output static browser run failed after 36 completed images:
Python MemoryError was followed by SQLite disk I/O errors and renderer asset
failures. The fixture repeats four imported printings with fresh face identities.

Test-only sampling showed a 5.4 MB database, nearly flat tracked object counts,
and Wasm heap capacity rising from about 2.3 GB at the first save toward 4 GB.
Explicit full collection did not stop growth; traced allocations remained
around 2 MB. A separate actual static worker isolated database reads.

| Isolated stage | Wasm heap capacity |
| --- | ---: |
| After loading full review PNG | 79.0 MB |
| After 20 byte copies | 94.8 MB |
| After 20 Pillow decodes and full collection | 113.8 MB |
| After 500 WAL database reads | 196.7 MB |
| After switching to DELETE and 1,000 more reads | 196.7 MB |
| After 20 forced checkpoints and 100 API responses | 196.7 MB |

These are decimal MB and heap capacity, not actual process RAM or end-to-end
throughput. Freed Wasm capacity does not shrink. The controlled comparison
isolates repeated WAL opens as the growth trigger; it does not establish the
precise allocation inside the underlying SQLite/Wasm implementation.

BrowserStore now switches to SQLite's DELETE rollback journal after opening the
workspace, then checkpoints the migration. The browser already serializes its
requests and excludes a second writer/tab. Transactions and complete metadata
checkpoints remain; the old local server's Store continues using WAL.

A fresh actual browser regression warms with 2,000 reads and performs another
2,000: heap stays at 78,970,880 bytes. The gate permits at most 32 MiB growth.
A routine regression verifies migration of saved WAL records, transaction rollback,
checkpoint contents and reopening the saved snapshot. Existing render rollback,
interruption, quota and reload checks are included in the final full sweep.

[Raw isolated measurements](browser-database-memory-profile.json) retain the
baseline, test scope and interpretation. The corrected 400-output stress run
and all-enabled sweep are still in progress; final results will be appended.