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

## After chunk 4 measurements

Render/save overlap remains experimental: fresh browser writes showed less than
one percent difference and longer individual save calls. Prioritize native iframe
long-task boundaries and UI remount/input retention next. Use fresh-write trials
and exact RGBA/saved-byte/reload checks for further pipeline experiments.

## After chunk 6 measurements

Native stage boundaries reduce the longest reported individual task, while
remaining timer gaps still require investigation. Next cover synchronous GitHub
setup and archive job families with safe cancellation/publication boundaries,
then measure renderer concurrency and worker feasibility. Keep fresh-write,
pixel/hash/reload comparisons and reserve the final hour for the full sweep.


## After chunk 9

Remaining small library/order previews and stable order filtering are verified.
Next measure startup cold/warm and investigate the earlier unexplained timeout;
reserve sufficient time for all-enabled stress, recovery, live and large-file
verification before the morning checkpoint.
