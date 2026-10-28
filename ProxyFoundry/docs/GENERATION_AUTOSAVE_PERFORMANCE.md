# Generation autosave regression bisection (2026-10-28)

The first bad commit is `6cbe23d` (automatic complete data.json saving).
Its parent `0ba1c1b` retains the original database batching behavior. Bisection
started at `4f0219c`, before the changes in this maintenance chat, and ended at
the then-live `dc7dcae`.

## Measured comparison

The benchmark uses the existing native-render profiler's seven structural faces:
creature, land, Saga, Planeswalker, Station, Godzilla and Prepare. The walker has
a passive first ability so the original version's known first-badge fit bug does
not block the comparison. All revisions receive the same fixture. Every run
invalidates preparation and removes generated images outside the measured
interval, then calls the production `renderDecks` and saves seven fresh PNGs.

The database includes six MiB of padding, as in the existing whole-generation
benchmark. Browser, fixtures and instrumentation stay constant. Tests run
sequentially in isolated headless Edge OPFS workspaces. This is not the user's
selected-folder workspace and does not establish whole-deck durations.

| Revision | First pass, seconds | First-pass DB writes | Warm median, seconds |
| --- | ---: | ---: | ---: |
| Original `4f0219c` | 9.394 | 1 | 7.218 |
| Midpoint `0ba1c1b` | 10.083 | 1 | 6.869 |
| First bad `6cbe23d` | 16.821 | 19 | 7.415 |
| Previous live `dc7dcae` | 16.613 | 19 | 7.856 |
| Batching fix on `dc7dcae` | 10.693 | 1 | 7.011 |

These forced-regeneration runs have one first pass and three warm repetitions.
The first pass includes derived-artwork processing and native asset warmup;
metadata and raw source artwork have already been seeded. The 19 database writes
in the previous-live first pass take 6.581 seconds. Warm runs retain source and
renderer caches but still prepare and save fresh PNGs.

The ordinary Generate path, with forced regeneration disabled and generated
images removed before each timed run, confirms the result:

| Revision | First pass, seconds | First-pass DB writes | Warm median, seconds |
| --- | ---: | ---: | ---: |
| Original `4f0219c` | 8.851 | 1 | 6.743 |
| Previous live `dc7dcae` | 17.579 | 19 | 7.689 |
| Batching fix | 9.075 | 1 | 7.032 |

Ordinary Generate has two warm repetitions per revision. All reported runs finish
with seven saved faces and no card errors. Wall times remain subject to hardware
and scheduling variation; the change in actual durable-write count is consistent.

## Cause and repair

`6cbe23d` moved `/api/generation/begin` after preparation. BrowserStore therefore
performed preparation without its deferred-checkpoint transaction. Asset and
document updates repeatedly rewrote the database instead of being included in
the final generation commit. The same code movement also bypassed preparation's
generation-specific GitHub artwork prefetch branch; that network effect is not
quantified by this fixture.

The repair restores transaction opening before preparation. For linked decks,
rendering still waits until preparation, readiness checks and the complete
GitHub recipe save succeed. Source-image URL registration and canonical data.json
source updates may join that transaction; unrelated card/layout/deck edits remain
blocked. Failure or cancellation rolls back the local transaction. No pipeline
version or render-cache invalidation is introduced.

## Scope and checks

The fixture has a linked optional GitHub folder. External GitHub freshness is held
constant and no remote repository writes occur. This isolates local preparation,
rendering and persistence; it does not measure GitHub upload latency or source-URL
dialogs. Existing automatic-save checks separately verify that a failed or
cancelled GitHub save prevents rendering. BrowserStore tests verify that source
metadata stays batched, real permanent-image source verification succeeds within
the transaction, unrelated edits remain blocked, and abort restores prior metadata.

Reproduction uses the seed/structural fixtures in `profile_native_render.py`,
the isolated production-generation approach in `benchmark_generation.py`, and
temporary builds from the revisions above. Count actual `BrowserStore.persist`
calls rather than attempted `checkpoint` calls: unchanged/deferred checkpoints
do not imply a disk write. Keep fresh-save and cached-output trials separate.

## Full Hulk Pack preparation follow-up

Diagnostics (5) recorded a 435.264-second preparation job for Hulk Pack: 100
cards, 118 faces. The retained application log covers only the final part of that
job. In that retained interval, 27 `card.prepare` entries accompany 136 timed
database checkpoints totaling 72.86 seconds. Artwork resolution totals 78.87
seconds and card preparation totals 92.80 seconds. These timings overlap; they
must not be added. The late land-card compilation calls are below the normal
0.1-second logging threshold. Repeated full snapshots, together with serial
artwork acquisition, explain the observed preparation slowdown.

A read-only snapshot of the actual workspace database and the real Hulk Pack
inputs was replayed in isolated Edge OPFS. Remote artwork bytes were served from
the read-only workspace, and GitHub JSON freshness was frozen across revisions.
The original workspace was never modified. This measures the real preparation,
normalization and browser persistence paths, while excluding internet variance.

| Version/path | Cold preparation | Cached-art layout rebuild | Unchanged check |
| --- | ---: | ---: | ---: |
| Original `4f0219c` | 20.540 s | 12.748 s | Not measured |
| Fixed `2a829e1`, explicit generation batch | 20.267 s | 13.305 s | Not measured |
| Backend-guarded direct preparation | 20.878 s | 12.787 s | 0.746 s |

Each cold/rebuild run makes one durable metadata write. The unchanged check makes
none. Original `4f0219c` has its known Tezzeret planeswalker-fit error; the fixed
runs prepare all 118 faces without errors. These are preparation measurements,
not full PNG-generation durations, and the live internet can add download time.

Browser direct preparation now opens and owns a preparation-only transaction
when its caller has not already opened one. This preserves deferred metadata
writes, six-slot artwork prefetch and generation-aware job scheduling regardless
of the caller. It commits once after success and rolls back on cancellation or
failure. Existing full-generation transactions retain ownership. The engine
tracks actual backend transaction state so thumbnails remain deferred during
either path and resume afterward. Cancellation/failure tests verify no leaked
transaction, and a real 118-face browser replay verifies the direct path.
