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


- Remaining small library/order tiles now use thumbnails; order filtering keeps
  image elements stable. Initial large-grid mounting and thumbnail creation are
  still separate costs. The current fixture proves reduced bytes and DOM work,
  not a reduction in native render time or initial 400-image decode latency.

- Repeated startup launches pass but do not establish the cause of the isolated
  timeout. Production stage/total diagnostics now expose future failures. Local
  bundle timings cannot justify a shared cache based on public network assumptions.


- The original 400-output browser run exhausted memory after 36 completed
  images. Repeated WAL database opens were isolated as the growth trigger;
  BrowserStore now migrates to DELETE rollback journaling. The corrected run
  saves/reloads all 400 outputs with a constant 136.7 MB Wasm heap. The precise
  SQLite/Wasm allocation remains unestablished. See BROWSER_DATABASE_MEMORY.md.
- Large-run navigation measured Templates 14.85s and return to cards 17.43s
  while the independent all-enabled sweep competed on an 8 GB machine. A
  separate actual static worker with 400 synthetic faces measured Templates
  0.0035–0.0067s, deck reads 0.273–0.786s and library reads 0.219–0.508s.
  That fixture has minimal compiled metadata and no real saved PNGs, so it
  does not establish how much of the large-run delay comes from native drawing,
  memory pressure, full snapshot size or individual browser scheduling.