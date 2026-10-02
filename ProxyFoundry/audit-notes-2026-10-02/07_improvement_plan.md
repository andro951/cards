# Ordered overnight plan

1. Measure scheduling baseline; introduce safe preparation chunks and verify
   foreground service, cancellation, persistence and stale-edit conflicts.
2. Replace global busy rejection with scoped work ownership, foreground priority,
   route-safe responses and owned activity/cancel behavior.
3. Keep all generation after setup choices; present one continuous preparation,
   rendering and save operation with meaningful persistent progress/completion.
4. Benchmark bounded save/render overlap, asset deduplication and download limits.
5. Profile startup, repeated menu reads, thumbnails, image decode and large grids.
6. Compare renderer concurrency 1/2/3 and worker compatibility without assuming
   DOM-native CardConjurer can run in a Web Worker.
7. Long sessions, queued cancellation, reload, interrupted saves and network/storage
   failures; test exports and recovery. Reprofile remaining largest bottlenecks.

After each verified milestone: commit and push main, update findings and measured
results. Begin final verification by 08:31 Eastern for a 09:31 checkpoint.
If one experiment is blocked, continue independent tasks without asking the
sleeping user for filesystem picker access.
