# Risks to investigate

- Synchronous network transport can make a single chunk long. Measure actual
  card, source-index and asset request spans before changing transport.
- Imports and runtime setup now yield; GitHub setup, orders, archives and backups
  still need their own safe yield boundaries.
- Same-deck generation/edit races require optimistic revisions and ownership.
  Shared asset caches may gain orphan bytes on conflict but must not lose edits.
- Pipelines need bounded in-flight Blobs; failure/cancel must settle pending
  saves and preserve durable completion semantics.
- Multiple iframe rendering may worsen input latency and memory. Test one,
  two and three before shipping any parallelism.
- Browser timing differs from visible Windows Chromium; avoid mixing the known
  anomalous headless native export measurements into performance claims.

- Actual pipeline traces show near-one-second UI timer gaps with the longest
  tasks attributed to the CardConjurer iframe. Test safe task yields between
  native stages before considering additional renderers; preserve exact pixels.
- Identical-output reruns deduplicate saved assets and overstate overlap benefits.
  Use fresh generated PNG writes with warm input caches for throughput decisions.
