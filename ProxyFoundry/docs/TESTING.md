# Test groups and timings

The [per-test timing list](test-timings.csv) records observed durations from the
2026-09-29 full sweep and subsequent affected regression runs, refreshed on
2026-10-02. Each row contains the pytest ID, group, seconds, outcome, and timestamp.
Times vary with the machine, disk, browser, and network. Historical extended
measurements are retained when that test was not affected or rerun.

| Group | Current tests | When to run |
| --- | ---: | --- |
| Routine | 609 | Every completed change |
| Extended | 124 | Relevant changes or an explicit full sweep |

The artwork-matching checkpoint adds schema/UUID/token-variant/filename checks,
metadata-only inventory review, indexed 5,000-image lookup and 2,000-entry selector
regressions. Browser coverage includes pairing, undo/resume, explicit fallback,
bounded thumbnail DOM, refreshed-image invalidation, local permission denial,
GitHub merge/SHA behavior, one-update and remembered connections, and actual
static-site save/reload persistence without rendering. The full routine suite
and affected DOM, GitHub import and static browser cases are run for this change;
this is not another full extended sweep. Live authenticated GitHub writes are
not performed; the write protocol and UI are tested with API fixtures.

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
