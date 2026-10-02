# Risks to investigate

- Synchronous network transport can make a single chunk long. Measure actual
  card, source-index and asset request spans before changing transport.
- Imports, runtime setup, GitHub setup, paired orders, deck image archives and
  backup export now yield. Backup inspect/restore and legacy tools still need
  their own safe boundaries; do not yield inside a mutation transaction.
- Same-deck generation/edit races require optimistic revisions and ownership.
  Shared asset caches may gain orphan bytes on conflict but must not lose edits.
- Pipelines need bounded in-flight Blobs; failure/cancel must settle pending
  saves and preserve durable completion semantics.
- Multiple iframe rendering may worsen input latency and memory. Test one,
  two and three before shipping any parallelism.
- Browser timing differs from visible Windows Chromium; avoid mixing the known
  anomalous headless native export measurements into performance claims.

- Native stage yields reduce the longest reported task from about 600 to 350ms
  with exact pixels preserved. Timer gaps still sometimes exceed a second;
  synchronous native calls remain on the main thread. Measure remaining causes
  before considering additional renderers.
- Identical-output reruns deduplicate saved assets and overstate overlap benefits.
  Use fresh generated PNG writes with warm input caches for throughput decisions.

- Card progress still fetches a complete deck snapshot per image. Measure a lean
  progress response or saved-face update before changing its revision/review
  semantics. Stable DOM fixes remount/input loss but does not eliminate that read.
- Collections retain their mounted tiles while filtering. Initial mount and very
  large-collection memory remain separate profiling targets; no virtualization
  benefit is claimed by the 400-card/300-deck fixture.

- The complete /cards/ deployment test timed out at startup once after app
  modules loaded, then passed on rerun. Cause unproven; do not dismiss it as
  network slowness without evidence. Failure artifacts now capture the body,
  screenshot, browser errors and persisted browser diagnostics. Recheck in the
  final full sweep and investigate any recurrence.
