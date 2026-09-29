# Test groups and timings

The [per-test timing list](test-timings.csv) records 452 measured tests from the
all-enabled run on 2026-09-29 and later targeted regression runs.
Each row has a pytest test ID, group, measured seconds, outcome, and measurement
time. These are observed times on one Windows machine, not limits or guarantees.
The 440-test complete run took 23 minutes 54 seconds; the sum of individual
test times is slightly less because pytest also spends time on collection and
reporting.

| Group | Tests | Sum of measured test times | When to run |
| --- | ---: | ---: | --- |
| Routine | 401 | 2 minutes 26 seconds | Every completed change |
| Extended | 51 | 22 minutes 27 seconds | Relevant changes or an explicit full sweep |

The extended group contains browser UI, the installed print extension, real
CardConjurer rendering, live GitHub/dependency checks, and the 2.3 GiB transfer
stress test. Its three longest tests are the native 19-face deck (6 minutes 48
seconds), native Station rendering (2 minutes 57 seconds), and the production
website smoke (2 minutes 41 seconds). The grouping lives in
[`scripts/test_policy.py`](../scripts/test_policy.py) and is applied by pytest
at collection time.

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
`PF_LARGE_TRANSFER=1` for the multi-gigabyte archive. The Chromium tests also
need Playwright's Chromium installed; on Windows, set
`PF_BROWSER_EXECUTABLE` and `PF_DOM_EXECUTABLE` to its executable path for the
component tests.

For a full sweep, use `RUN_TESTS.bat` option 3. Option 1 runs routine tests;
option 2 runs only extended tests. Options 2 and 3 enable all browser, live
dependency, and large transfer flags. They take much longer and need Chromium,
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
