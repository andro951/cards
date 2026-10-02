# Recheck and continuation log

## Chunk 1 — baseline and preparation scheduling

Baseline main: 893adad. Started 01:31 Eastern. Real static Pyodide browser
fixture: /api/decks mean 2.503 seconds during a two-second whole job; cancellation
acknowledgment 1.7–2.9 ms. The separate cancellation control plane already works.

Resumable fixture: menu request mean 0.114 seconds (95.5% less waiting for this
fixture), cancellation acknowledgment 1.7–3.8 ms. Each artificial chunk is 100 ms;
these numbers describe scheduling, not actual deck-generation throughput.

Implemented resumable BrowserJobs, worker timer turns, and preparation generators
with saved-card yields. Local synchronous prepare drains the same steps. Added
generator result/fairness/cancel/failure tests and actual preparation saved-state,
intervening revision conflict and cancellation-after-last-card tests.

Verification: 542 routine cases passed in 197.75 seconds; all 12 focused job and
preparation cases passed in 11.69 seconds, including the four further routine
cases added during that run. All 546 current routine cases are covered. The real
static scheduling and cancellation/reload checks passed in 48.15 seconds.
JavaScript syntax, Python compilation and the four canonical vendor hashes pass.
All three real static import/setup/generate/review/paired-ZIP/reload flows passed
in 192.24 seconds, including the GitHub Pages /cards/ path. They confirm setup
does not generate, production preparation completes and output/export survives
reload. No native rendering or artwork-placement code changed in this chunk.
The chunk is ready to commit and push main.
Next: scoped UI/job ownership, route safety and additional long-job families.

## Chunk 2 — scoped UI ownership and route safety

Baseline main: 943646d. Replaced global busy guards with task ownership,
per-deck mutation leases and a single cancellable native-render queue. Independent
deck imports, setup, deletion and order operations remain usable during generation.
Whole-workspace restore and location changes hold exclusive access. The location
lease is released before reload and on picker cancellation. Backup cancellation
uses its own task token, including while the workspace is exclusively held.

The activity panel belongs to the visible foreground task and restores retained
background progress when that task finishes. Queued generations have individual
cancel buttons; duplicates and same-deck changes produce a specific conflict.
Late deck/templates/settings/orders responses no longer replace a selected page.
Generation completion preserves an open dialog and unsaved setup; navigation to
the completed deck is explicit. Added generation.total timing around the whole
preparation/render/save operation. Render/save overlap remains unchanged.

Verification: 550 routine tests passed in 199.68 seconds. Nine affected browser
cases passed in 109.24 seconds; two offline DOM cases initially skipped because
their opt-in flag was absent, then both were enabled and passed in the four-case
ownership run (46.41 seconds). That run also verified real native generation,
foreground cancellation, queued cancellation, exclusive backup cancellation,
and workspace-picker exclusion/release without any native permission prompt.
The existing deletion/order-filter/recovery case passed during unrelated work.
The delayed-response test confirmed navigation wins over old deck/template reads.
Six Node adapter/helper cases, JavaScript syntax, Python compilation and all four
canonical vendor hashes pass. The held-render screenshot was visually inspected:
orange appearance is intact and the other deck's unsaved setup remains visible.
Two completion notifications remain to consolidate in the next chunk.
All three current production static import/setup/render/review/paired-ZIP/reload
flows passed in 165.77 seconds, including normal/custom looks and the GitHub
Pages base path. Six final DOM/ownership cases also passed after the final legacy
backup ownership adjustment. No PNG/native drawing or art placement changed.

## Chunk 3 — metadata and runtime chunks, foreground job priority

Baseline main: 9654933. Sources.import_deck_steps yields after manifest parsing
and each resolved row, including duplicate rows. Workspace.create_steps keeps
the deck unpublished until import completes. Add Cards holds its starting
optimistic revision through resolution. Synchronous local wrappers drain the
same operations. Existing deck.import timing now spans all generator chunks.
Runtime.prepare_steps yields after each pinned dependency and checks cancellation
before returning ready. Browser routes use these generators; the old server's
threaded/synchronous interface retains its original operation types.

BrowserJobs gives foreground metadata/import jobs priority over background
deck/runtime preparation at safe boundaries. Equal priorities rotate. Cancelled
jobs close before new work to release resources promptly. Individual synchronous
network calls remain non-preemptible; this is not parallel card rendering.

Verification: 558 routine cases passed in 195.15 seconds, including eight new
priority/import/runtime tests. Focused tests prove duplicate quantities/sections,
metadata cache reuse after cancellation, no partial published deck, retained
intervening edits, inclusive import timing and cancellation after the final file.
Five affected actual static browser flows passed in 218.41 seconds, covering all
three full import/render/review/ZIP/reload variants, concurrent UI work and
cancellation/reload. The additional 12-row metadata-import browser fixture
passed in 19.13 seconds; a foreground settings read took 0.185 seconds while only
two of twelve rows had resolved. No rendering or artwork acquisition occurs in
that import. Python compilation and all four canonical vendor hashes pass.

The approved live filesystem browser is still connected at CDP 9227 with granted
read/write access to the benchmark folder. No new native picker was opened.
Next: benchmark bounded render/save overlap in browser and selected-folder
storage, then choose a production change only from measured integrity/timing.
