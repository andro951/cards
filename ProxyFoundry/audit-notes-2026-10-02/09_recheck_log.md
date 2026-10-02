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

## Chunk 4 — bounded render/save and asset-prefetch experiment

Baseline main: f503693. Added a standalone temporary static-build harness for
visible Chromium, reusing the already-approved CDP filesystem session. Production
rendering and saving are unchanged. Tested seven structural faces using original
Supernatural artwork, two warm repetitions per mode, plus a cold serial trial.
The experiment permits at most one older pending PNG save. Asset prefetch is a
benchmark-only bridge hook and begins only during explicit generation.

Caught a benchmark confound: repeated identical outputs reuse stored PNG assets.
Reran browser and filesystem trials with generated PNG assets removed outside
measurement, keeping input caches warm. Fresh browser means were serial 11.711s,
overlap 11.648s and overlap/prefetch 11.642s for seven faces. Fresh selected-folder
means were 19.077s, 20.771s and 18.942s. The small prefetch differences are not a
reliable benefit; plain filesystem overlap worsened timing. Keep production
serial and target native main-thread pauses next. No overlap experiment is shipped.

Verification: all 196 PNGs passed exact four-channel pixel comparisons and
production saved-byte hash checks; final seven outputs in all four runs survived
reload with unchanged bytes. Native long-task attribution is the CardConjurer
iframe, with UI timer gaps near one second. Dependency/plan warmup and result
collection are excluded from pipeline timings. Original selected-folder preference
is restored and its granted browser session remains open without a new picker.
Harness Python compilation and all four canonical vendor hash checks pass.
The prior chunk's 558 routine/affected browser results still cover unchanged
production code; this chunk adds measured experiments and documentation only.
See docs/GENERATION_PIPELINE_PROFILE.md and generation-pipeline-profile.json.

## Chunk 5 — stable collection updates and input retention

Baseline main: d1888b3. Cards and library searches/filter changes retain mounted
tiles and controls. Image progress patches thumbnails, status/counts and filters;
library progress no longer reads templates. The current view receives updates even
if generation started on another page. Its failed read logs without stopping
production generation. Only the current card-grid updater retains its DOM; route
changes release it. Same-deck mutation leases and unsaved-setup protections remain.
Deck completion preserves focused inputs/open dialogs and avoids duplicate notices.

Measured offline DOM/JS work against the previous committed UI, using identical
400-card and 300-deck fixtures in balanced two-repeat trials. Twenty card updates
fell from mean 0.682s to 0.046s; 40 card search changes from 0.683s to 0.018s.
Twenty library updates fell from 0.254s to 0.145s and eliminated 20 template reads;
40 library search changes fell from 1.430s to 0.016s. New progress retains search,
focus and card button identity with zero main remounts. This excludes initial
mount, network, rendering and persistence; it is not deck throughput. Raw timings
and scope are in docs/COLLECTION_RESPONSIVENESS.md and collection-update-profile.json.

Verification: all 558 routine tests pass in 178.50s. All 14 affected UI/browser
cases pass across the final runs: four offline controls/large-collection cases,
three existing browser search/hover/mobile controls, three actual static native
concurrency/search/cross-view cases, late response navigation and three complete
normal/custom/GitHub Pages import/setup/generate/review/ZIP/reload flows. The
library-to-card case injects one failed progress read and still finishes generation
with retained focus/caret and updated final counts. Screenshot checks wait for the
rendered thumbnail to decode. Python compilation, touched JS syntax and all four
canonical vendor hashes pass. No native frame/art/canvas implementation changed.
Final hover check: seven focused cases pass in 12.58s, including a preview
whose back becomes available during progress without replacing its button.
The decoded screenshot was visually inspected: rendered card, orange appearance,
focused search and one success notification are intact.
Next: native task-yield experiment and remaining long-job families/recovery.

## Chunk 6 — native stage task boundaries

Baseline main: 1d7d389. Yield a browser task after each existing measured native
stage, using scheduler.yield when available and a zero-delay timer otherwise.
No native drawing calls, order, readiness checks or pixels changed. Compared
stage yields, extra drawing yields and timer yields against fresh serial saves.
Mean longest reported native task fell from 588 to 357ms in browser storage and
623 to 347ms in selected-folder storage. Seven-card warm browser time is similar
(11.674 versus 11.599s); folder time was 2.8 percent slower (19.011 versus 19.543s).
This improves task boundaries, without claiming faster generation or solved input
latency. Some timer gaps remain over one second. Extra drawing yields are not shipped.

All 175 pipeline PNGs match serial pixels and production stored-byte hashes;
final outputs survived reload. The approved filesystem session was restored,
remains granted, and stayed open without a picker. The keyboard experiment has
an automation/status-probe confound and cannot establish end-to-end input latency.
Broad regression: all 132 PNGs from 22 structural faces match exactly under
original scheduling, stage yields and forced timer fallback (342.87s).
All 558 routine tests pass in 172.56s. Godzilla full-card art and blue Prepare
examples were visually inspected. See docs/NATIVE_TASK_YIELDS.md and raw reports.
Seven affected actual static browser cases pass in 260.92s: three complete
import/setup/generate/review/ZIP/reload flows, three foreground/cancel ownership
cases during real generation, and browser job cancellation/reload. Touched Node
syntax, Python compilation and git diff whitespace checks pass.

## Chunk 7 — cooperative GitHub setup and archive exports

Baseline main: dee035c. Browser jobs use generator paths for GitHub setup and
four-symbol imports, paired order packaging, original/art-crop/review image ZIPs,
and backup export. Legacy local routes drain the same implementation. Cancelled
generators remove unfinished archives in finally blocks, including the final
item boundary. Order publication rejects changed/deleted deck revisions. Immutable
snapshot assets are pinned while an export reads them, then deferred cleanup is
released; foreground deletion cannot remove an input still needed by that export.

New tests caught and repaired a review-generator cleanup variable omission.
All 22 new routine cases pass, including both complete/cancel paths on seven
routes, full-storage errors, final cancellation, stale order snapshots and
backup/review integrity during foreground deletion. Temporary actual static
benchmark adds 75ms per remote read: foreground deck reads dropped from
0.960–1.790s to 0.140–0.142s during setup, and 3.271–3.303s to 0.216–0.257s
during 24-image review export. Cooperative reads return before job completion.
All cancellation trials finish and cancelled review ZIPs are removed. These
are queue measurements, not live network or archive throughput claims.
See docs/COOPERATIVE_IMPORT_EXPORT.md and job-family-profile.json.
Final routine sweep passes all 580 cases in 245.25s. The initial ten affected
browser cases pass in 258.50s (new family benchmark, three complete static flows,
six existing GitHub draft/save cases). After asset protection, the benchmark and
two complete flows pass; the /cards/ case times out at startup once and then
passes in 56.55s. Its cause is not established. Added startup failure screenshot,
body/errors/browser diagnostic capture; retain startup recurrence as a stability
investigation for the final sweep. The approved anchor/folder session is alive
and granted. Python compilation and git diff checks pass.

## Chunk 8 — renderer concurrency and worker compatibility

Baseline main: dcb449b. Two balanced temporary static runs compare one, two and
three native iframes, priming every face in every iframe before measurement.
Final means for seven production-resolution faces: 6.099, 6.241 and 7.099s.
Two are 2.3 percent slower; three 16.4 percent slower, with longer reported tasks.
Keep production at one renderer. Distinct DOM/global canvas pixel surfaces
estimate 334/669/1,003 MB; this is not actual process RAM/GPU allocation and
excludes decoded images/caches. Main-thread task time is not total process CPU.

All 42 measured PNGs match every RGBA channel in each run. A dedicated worker
with OffscreenCanvas available cannot initialize the pinned creator script:
window is not defined. The adapter's DOM/control/font dependencies also remain.
No native rewrite or parallel production change is justified by these results.
The new extended gate passes in 400.02s; harness/test Python compilation and all
four vendor hashes pass. The prior 580 routine results cover unchanged production.
Next: remaining full-resolution UI previews, startup recurrence and final stress
and recovery sweep. See docs/RENDERER_CONCURRENCY.md and raw measurements.


## Chunk 9 — small previews and stable order filtering

Baseline main: 2098941. Library initial covers/backs and both order grid paths
now use the existing thumbnail API. Enlargement and exported originals retain
full resolution. Browser order search hides mounted tiles: 400 cards / 40 inputs
average 0.183s to 0.017s; child-list mutations 8,240 to zero, image identity/focus
retained. This is isolated DOM work, not initial load or generation throughput.
A 7,042,974-byte native PNG produces a 431,126-byte 420 x 588 tile; cold preview
creation 0.284s, cached reads 0.0034–0.0038s. Original bytes unchanged.
Fixed extended component harnesses to include actual WorkCoordinator imports.
580 routine cases pass in 209.24s, 16 component cases in 28.07s, five browser
cases in 185.06s including all three complete static deployment flows.
Actual review screenshot inspected: card image, text, actions and modal layout
are legible and correctly proportioned. Static tests prove small preview decode,
full-size enlargement, and ZIP bytes. No startup failure in these three flows.
See docs/SMALL_PREVIEWS.md and raw measurements. Startup recurrence and final
stress/recovery sweep remain next.


## Chunk 10 — actionable startup diagnostics

Baseline de4e47c. Twelve root/subpath initial/warm launches before and twelve
after instrumentation completed without startup timeout. Pyodide and Python
app initialization dominate; local bundle fetch/unpack is about 0.2s. No cache
or dependency rewrite is justified by this fixture. Production reports stages,
storage type, engine total/outcome/last stage and website total in browser
diagnostics, with clearer status messages. Timer boundaries and shared-process
CDN caching limitations are documented in docs/STARTUP_PROFILE.md.
Seven deterministic Node cases verify browser/folder success and five failure
stages. Actual root/subpath cold/warm diagnostic assertions pass in 56.36s.
580 routine cases pass in 242.94s; the new startup case is extended and separate.
Earlier isolated timeout remains unexplained, with failure capture retained.
A separate 400-image stress expansion is in progress: the original 180-second
pre-render wait expired, while the instrumented rerun proves preparation is
progressing (220/400 observed). Stress harness changes remain uncommitted until
its final state/reload and foreground interactions are verified.
