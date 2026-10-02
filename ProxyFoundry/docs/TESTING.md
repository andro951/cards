# Test groups and timings

The [per-test timing list](test-timings.csv) records observed durations from the
2026-09-29 full sweep and subsequent affected regression runs, refreshed on
2026-10-02. Each row contains the pytest ID, group, seconds, outcome, and timestamp.
Times vary with the machine, disk, browser, and network. Historical extended
measurements are retained when that test was not affected or rerun.

| Group | Current tests | When to run |
| --- | ---: | --- |
| Routine | 558 | Every completed change |
| Extended | 100 | Relevant changes or an explicit full sweep |

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
