# Test groups and timings

The [per-test timing list](test-timings.csv) records observed durations from the
2026-09-29 full sweep and subsequent affected regression runs, refreshed on
2026-10-03. Each row contains the pytest ID, group, seconds, outcome, and timestamp.
Times vary with the machine, disk, browser, and network. Historical extended
measurements are retained when that test was not affected or rerun.

| Group | Current tests | When to run |
| --- | ---: | --- |
| Routine | 907 | Every completed change |
| Extended | 171 | Relevant changes or an explicit full sweep |

The unchanged-deck planning pass passed 903 routine cases with four skips in
542.28 seconds. Focused preparation/scheduling checks passed 26 cases, and the
Chromium reload check passed for 121 prepared faces with no card processing or
deck saves. Its isolated OPFS planning/completion time was 0.6693 seconds; it
uses shared synthetic artwork and excludes the user's GitHub check and selected
workspace. See [preparation performance](PREPARATION_PERFORMANCE.md).

The 2026-10-06 preparation cache pass completed the routine suite with 897 passed
and four skipped cases in 512.18 seconds. Preparation-only live-source timings,
cache behavior, and follow-up opportunities are recorded in
[preparation performance](PREPARATION_PERFORMANCE.md).

Generate Images pauses background metadata at a card checkpoint and checks
setup requirements, including custom artwork credits, before waiting for the
remaining metadata. Required credit and artwork-matching dialogs now stay open
until valid choices are provided. The normal suite passed 901 cases with four
skips in 506.64 seconds. Popup policies and the full inventory are documented in
[dialog behavior](DIALOG_BEHAVIOR.md). All 49 focused browser UI cases passed (47 dialog/order cases plus two
confirmation-dismissal cases). Browser checks cover backdrop clicks,
Esc/X, required-step validation, replacement prevention, busy saves, nested
printing pickers, enlarged images and order review geometry.

Modern full-art tokens use the filled native rules box for any rules or flavor
text, including a single keyword. Empty/whitespace-only tokens keep the larger
art variant. Coverage includes text preservation, geometry, conversion,
refreshing old converted renders, template seeds and actual native PNGs inspected
visually. Classic and borderless styles retain their existing short-text rules.

Custom-art Station textbox checks cover neutral, single-color and dual-color
frames, one native-alpha textbox above a frame-only cutout, and idempotence.
Actual Station land renders include nicknames, custom artwork and a pixel check
that rejects opaque/stacked textboxes. Template version 8 refreshes cached
automatic Station images. The Scryfall underframe policy is preserved.

All downloads use normal browser downloads regardless of size; there is no app
save-location picker. Original printing, cropped-art and review-image downloads
use temporary staging without creating print orders or leaving files in `orders`.
Saved print orders retain their snapshots, and downloading them sends a separate
copy to Downloads. Backups, diagnostics, helpers and JSON exports follow the same
normal download flow.
Checks cover HTTP and static website downloads, cleanup after success/failure,
cancellation, expiry of abandoned exports, and keeping temporary browser staging
outside the selected workspace folder. The static browser also verifies reload
cleanup and download contents. Large-file routing uses size metadata in the UI
test; this change does not rerun the separate 2.3 GiB transfer stress test.

The staged-import milestone passed all 648 routine cases in 341.08 seconds,
30 offline UI cases in 126.99 seconds, three focused browser cases in 31.82
seconds, and three actual static website import/generation/review/export flows
in 295.91 seconds, including the GitHub Pages `/cards/` path. New checks cover
list-only fetching, background metadata edits, cancellation/recovery, duplicate
printings, two-sided cards, deferred data.json validation, and absence of card
artwork downloads or rendering before Generate Images. Full metadata timing is
recorded once as `deck.metadata`; the initial list fetch is `deck.list.fetch`.

Explicit Godzilla two-sided frame checks cover transform, modal DFC, double-faced token, and reversible faces; independent creature/land text and stats; optional nickname overlays; full-card fitting; static picker selection and autosaving; and a real two-face CardConjurer render inspected visually. Automatic keeps its existing structural frame rules.

Art & Setup layout checks cover desktop and mobile section order and widths, adjacent Other Options, collapsed Format help, artist autosaving, reachable expanded token controls above the sticky footer, and no image generation while configuring the deck. Desktop and mobile screenshots are visually inspected.

Modern full-art token text checks cover black body text, white names without outlines or shadows, nickname overlays, short/long rules geometry, and deck-wide token conversion. Pipeline v33 refreshes previously generated images; a genuine native render is visually inspected.

Outlined italic rendering checks generate actual Spirit, Construct, and legendary Godzilla cards, inspect native stroke calls for rounded joins, and save final PNGs for visual inspection. Pipeline v32 invalidates cached images with the previous sharp outlines.

Normal Look starts image generation automatically after deck import, using normal artwork and frames without entering Art & Setup. Customize Look still defers generation until Generate Images. Offline DOM and HTTP regressions cover both paths; the production static website checks automatic completion followed by explicit customized regeneration.

Frame regeneration checks cover token picker/dropdown synchronization, saving before regeneration, new cache keys for changed styles, preserving the selected token frame when adding nicknames, topmost real-name addons, and Godzilla main titles without the real-name strip. Native Chromium checks regenerate an existing token in both modern styles and inspect Godzilla/nickname renders; the static website checks the derived pinned title assets.

Setup persistence regression checks cover both Generate Images buttons saving the latest edits before preparation, navigation preserving edits, storage failure blocking generation with retry, and one-click GitHub import saving before reporting completion. Pending one-click links are imported before either Generate Images button prepares a deck, retaining the entered artist; failed imports stop generation, and already imported links are not imported again.

Card-reference export checks cover regular cards, token variants, two-sided face names, multiple selected printings, records without Oracle IDs, retained metadata, repeat exports, all three destinations, and 5,000-card indexed enrichment. Import checks accept reference-only entries and reject invalid Scryfall URLs.

The artwork-matching checkpoint adds schema/UUID/token-variant/filename checks,
metadata-only inventory review, indexed 5,000-image lookup and 2,000-entry selector
regressions. Browser coverage includes pairing, undo/resume, explicit fallback,
bounded thumbnail DOM, refreshed-image invalidation, local permission denial,
GitHub merge/SHA behavior, one-update and remembered connections, and actual
static-site save/reload persistence without rendering. The full routine suite
and affected DOM, GitHub import and static browser cases are run for this change;
this is not another full extended sweep. Live authenticated GitHub writes are
not performed; the write protocol and UI are tested with API fixtures.

The deletion/diagnostics update runs the affected coordinator, deletion and server
tests, all offline DOM checks, and the static-browser deletion/recovery test.
Coverage includes cancelling only the target deck's generation, waiting for task
settlement in the background, reading the current revision, keeping print-order
guards, and including browser notifications/errors in the engine diagnostics ZIP.

The subsequent GitHub source-selector and nickname-overlay fix passed all 591
routine cases in 240.97 seconds and all six offline DOM cases in 34.16 seconds.
New checks cover source selection during import, saved setup restoration, and
topmost nickname strips in final compiled Saga cards.

The final 2026-10-02 checkpoint covers all 704 collected pytest IDs with passing
results across the all-enabled overnight sweep and affected reruns, with no
uncovered/skipped IDs. The original sweep completed with 695 passes and three
failures; corrected harness and transport reruns passed. The final worker checks
cover all 23 website cases (21 passed directly; two standalone profiler import
failures passed after path repair), 17 storage cases, native exact-pixel/full-art
checks and four new standalone entrypoint regressions. All 20 Node cases and
four approved vendor hashes pass. This is full-sweep plus affected coverage,
not a claim that one final fresh all-enabled invocation was entirely green.

The overnight metadata/runtime scheduling milestone passed all 558 routine tests
in 195.15 seconds, including foreground job priority, import publication/revision
safety, scoped leases, native queue priority, cancellation and failure
cleanup. Affected static browser checks cover importing/editing during generation,
queued cancellation, wrong-task cancellation prevention, workspace picker
exclusion and cancellation release, unrelated deletion and stale route responses. The
extended group contains browser UI, printer-extension fixtures, real CardConjurer
rendering, live dependency checks, a 100-image browser-session stress check, and
the 2.3 GiB archive transfer. The 100-image test is intentionally expensive and
requires `PF_DECK_STRESS=1`; ordinary browser runs leave it out. The grouping lives
in [`scripts/test_policy.py`](../scripts/test_policy.py).

CI runs the routine group plus four focused actual static Chromium production
checks on every relevant push. The remaining extended group runs only when
**Run workflow → full_sweep** is selected, or when selected locally because a
change affects it. Production paths are verified in the browser, not solely
through the old local application's backend. The focused gate includes deletion and saved-order dependencies, response
integrity and response lifetime checks, while the long 100-image run remains
opt-in.

Run routine tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m routine --junitxml=test-results\routine.xml
```

Run a specific affected extended test by its ID from the CSV, after enabling
its required `PF_*` flags. For example, in PowerShell:

```powershell
$env:PF_BROWSER='1'
.\.venv\Scripts\python.exe -m pytest -q tests/test_extension.py
```

Use `PF_DOM=1` for offline DOM tests, `PF_LIVE_CC=1` for real CardConjurer
rendering, `PF_LIVE_GITHUB_SETUP=1` for the live GitHub smoke test, and
`PF_LARGE_TRANSFER=1` for the multi-gigabyte archive, and `PF_DECK_STRESS=1`
for the 100-image browser-session check. Use `PF_HEAP_BOUNDARY=1` for the
heap-above-2-GiB check that verifies high-address binary, upload, filesystem
job events and ASCII JSON integrity; it needs enough memory and remains in the extended group. The Chromium tests also
need Playwright's Chromium installed; on Windows, set
`PF_BROWSER_EXECUTABLE` and `PF_DOM_EXECUTABLE` to its executable path for the
component tests.

For native renderer or asset-readiness changes, also run
`tests/test_native_readiness.py` with `PF_BROWSER=1` and `PF_LIVE_CC=1`.
It opens visible Chromium, renders 22 structural faces twice, and checks exact
pixels against a delayed reference. The latest run took 325.26 seconds. Visible
Chromium avoids this host's abnormal headless canvas/export delays; these timing
results should not be mixed with headless measurements.

For native task scheduling changes, run `tests/test_native_task_yields.py` with
the same flags. It renders 22 structural faces twice under original scheduling,
stage yields and the timer fallback, comparing all 132 PNGs exactly. The latest
run passed in 342.87 seconds. See [native task boundaries](NATIVE_TASK_YIELDS.md).

`tests/test_native_concurrency.py` checks experimental one/two/three renderer
output equality and an actual worker compatibility probe with those same flags.
It passed in 400.02 seconds. See [renderer concurrency](RENDERER_CONCURRENCY.md).
This experiment supports keeping production serial.

For a full sweep, use `RUN_TESTS.bat` option 3. Option 1 runs routine tests;
option 2 runs only extended tests. Options 2 and 3 enable all browser, live
dependency, full-deck stress, and large transfer flags. They take much longer and need Chromium,
network access, and free disk space.

`RUN_TESTS.bat` updates the local timing list at `test-results/timings.csv`
after each run. Option 3 also removes obsolete test IDs after a complete sweep.
To update the committed baseline from a JUnit report:

```powershell
.\.venv\Scripts\python.exe scripts\update_test_timings.py test-results\full.xml --output docs\test-timings.csv --prune
```

The updater merges new measurements with the previous list, so a routine run
does not erase timings for extended tests. Skipped tests retain their last
measured duration; use `--prune` only with a complete all-enabled report.

The Node deck-adapter and browser-helper tests run after pytest in
`RUN_TESTS.bat`. With `PF_LIVE_DECK_SITES=1`, they also fetch real public
Archidekt and MTGGoldfish decks through the helper's bounded endpoint logic.
These live fetches run in the extended and full modes.
The affected five-card Supernatural full-art browser test passed in 338.24 seconds.
It downloads the actual review ZIP and checks rendered art pixels against full-card
source coordinates. Run `tests/test_full_art_examples.py` with `PF_BROWSER=1`
and `PF_LIVE_CC=1`; see [full-art verification](FULL_ART_VERIFICATION.md).

Slow application operations now have [timing logs](TIMING_LOGS.md), separate from the per-test timing CSV.

For GitHub setup or archive scheduling changes, run
`tests/test_job_families.py` and the affected static check
`tests/test_website.py::test_static_github_setup_and_review_export_service_foreground_requests`
with `PF_BROWSER=1` and `PF_LIVE_CC=1`. The latter compares real browser-engine
job families with controlled remote delays and verifies cancellation cleanup.
See [cooperative imports/exports](COOPERATIVE_IMPORT_EXPORT.md).

For worker scheduling changes, run
`tests/test_website.py::test_static_engine_foreground_requests_between_job_chunks`
with `PF_BROWSER=1` and `PF_LIVE_CC=1`. It exercises the real static service worker
and Pyodide engine using a temporary two-second job, requires foreground replies
between 100 ms chunks, and checks cancellation. The standalone reproduction is
`scripts/profile_responsiveness.py --cooperative --verify`. This is a scheduling
benchmark, not a deck-generation throughput measurement.

Native render saves now validate and preserve original PNG bytes, and unchanged database snapshots are skipped. See [save verification and benchmark](RENDER_SAVE_VERIFICATION.md).

### Render/save pipeline experiments

[Pipeline measurements](GENERATION_PIPELINE_PROFILE.md) distinguish existing
identical PNG assets from fresh writes in browser and selected-folder storage.
The standalone harness uses visible Chromium, exact RGBA comparisons, saved-byte
hash checks and reload verification. `--folder` reuses an approved CDP session
without opening a permission picker. These are opt-in performance experiments,
not an additional routine test or a change to the production render pipeline.

### Stable collection updates

[Collection responsiveness](COLLECTION_RESPONSIVENESS.md) records the isolated
400-card and 300-deck DOM comparison. Regressions verify stable search/caret,
selection, filters and inspector drafts during progress, plus real static
native generation and a failed progress read after switching from library to
cards. The collection milestone passed all 558 routine cases in 178.50 seconds
and all 14 affected UI/browser cases, including three complete production flows.


### Small previews and order filtering

[Preview measurements](SMALL_PREVIEWS.md) cover the remaining library and order
grid previews. Affected component tests include 400-card stable filtering and
original-image enlargement; complete static flows verify decode and ZIP bytes.
The milestone passed 580 routine tests, 16 components and five browser cases.


### Startup diagnostics

[Startup measurements](STARTUP_PROFILE.md) cover root/subpath initial loads and
reloads, persisted timers and failure-stage reporting. Node startup timing tests
run with the existing tests_web wildcard. The actual static startup test is
extended and requires PF_BROWSER=1 and PF_LIVE_CC=1.


### Repeated artwork normalization

[Image-ingest reuse](IMAGE_INGEST_REUSE.md) documents the bounded metadata cache
and actual static browser comparison. Routine image cases cover changed bytes,
trimming, missing files, invalid input and eviction. The actual static ingestion
check is extended; it verifies byte identity without a machine-dependent timing
threshold.


### Browser database memory

[Journal measurements](BROWSER_DATABASE_MEMORY.md) isolate repeated WAL opens
as the trigger for browser heap growth. Routine tests verify saved-workspace
migration and rollback; the extended actual browser case checks 4,000 reads
against a bounded heap-growth allowance. The opt-in deck stress test supports
PF_STRESS_IMAGES=400 and PF_STRESS_HEADFUL=1 for an expanded visible run.
Only its existing default 100-output case is part of an ordinary full sweep.
The larger fixture repeats four actual printings with fresh face IDs; it does
not claim coverage of 400 distinct artworks.

## Custom helper artwork (Day / Night)

Automatic helper cards use complete Scryfall printing scans when artwork comes
from Scryfall. Custom artwork uses the existing full-art floating bars and rules
panel with the actual face name, Card type, outlined white rules, and artist
credit. Artwork covers the full card canvas. This also applies to custom
Experience and Poison Counter helper artwork.

For Day / Night, use separate `day.png` and `night.png` files; numbered names
such as `121_day.png` and `122_night.png` also match. A missing Night image
requires Scryfall fallback or custom Night artwork. Night remains the printed
reverse of Day.

Verification: 594 routine tests passed in 232.02 seconds. Both native helper
render cases passed in 96.28 seconds, covering four Scryfall scans, four custom
art faces, numbered filename matching, and the Day/Night print-order pair.
Custom Day and Night output images were visually inspected. The initial custom
browser run stopped at the artist-credit prompt; the fixture now supplies its
artist before generation.


## Native frame component repairs (2026-10-03)

The compiler matrix exercises all ten color pairs across regular/tall planeswalkers,
Class, Battle, Flip, Station, Godzilla cards and Godzilla lands. It checks preserved
complete bases, idempotence, native crown blends, topmost nickname addons, modal
reminder isolation and independent Prepare spell colors. Eight genuine upstream
CardConjurer renders were inspected visually. Existing Prepare/Godzilla checks
passed; Station and both Station land checks passed on desktop Chromium after
headless Windows canvas loading hit the existing script timeout. These Station
harnesses now use the same desktop mode as the native structural suite on Windows.
The GitHub Pages website build succeeds. Vendor manifest hashes remain unchanged.
