# Native rendering workers

## Implementation

CardConjurer's pinned native drawing code now runs in dedicated Web Workers.
An adapter supplies its control defaults, image loading, fonts and canvas globals;
the renderer still uses the upstream composition and text layout functions.
The small host iframe supplies the security origin and decodes SVGs when needed.
SVG symbols are rasterized at their actual destination coordinates to preserve
fractional positioning. Frames, text, artwork and PNG encoding run in workers.

The application uses two workers on devices reporting more than 4 GB RAM and
multiple CPU threads, otherwise one. Browsers without Worker/OffscreenCanvas use
the existing DOM renderer. The pool supports up to four for controlled experiments;
four is not the production default on this 8 GB machine.

Each worker holds at most one completed PNG. Storage commits run sequentially.
Cancellation terminates workers and finishes an already accepted save before
returning. Failures stop outstanding render work and preserve completed saves.
Decoded unreferenced images are bounded to 64 MiB per worker, compressed runtime
images retain their existing 64 MiB limit. SVG destination variants have a
64 MiB budget and are pruned after export,
so eviction cannot affect the current card's final draw. Live frame images and
native canvases require additional memory.

The bridge suppresses image-loading redraw callbacks until inputs are ready.
Its existing two final native drawing passes remain. Deck-view refreshes are
throttled to once per two seconds instead of refreshing after every save.
The existing quick preparation plan and render cache continue to skip unchanged faces.

## Supernatural measurement — 6 October 2026

The original diagnostics identified 117 cards / 121 faces. An isolated workspace
reconstructed those faces using cached Scryfall printings, the repository's
`supernatural/data.json`, numbered artwork and set symbols. The original saved
deck was absent from the source database, so this is the recovered deck rather
than a claim to reproduce every setting of the historical run. The source
database was opened read-only.

Visible Chromium rendered all 121 faces at 2010 × 2814, including production
render-session loading, PNG export and filesystem saves. Both trials used the
same prepared inputs. The serial trial used the bridge from commit `a043a76`;
the parallel trial used two workers. Runtime dependencies were cached. Generated
renders and their asset files were cleared in the isolated workspace before
each trial, so both trials performed fresh image writes.

| Trial | Render and save elapsed | Saved faces |
| --- | ---: | ---: |
| Previous serial renderer | 210.623 s (3m 31s) | 121 |
| Two native workers | 129.220 s (2m 09s) | 121 |

Reduction: **81.403 seconds / 38.65%**, or **1.63× throughput**.
An immediate cached render plan took **1.769 seconds**, queued **zero** faces
and reused all **121** renders. Preparation, deck import and cold dependency
downloads are excluded from these render/save timings.

These are local filesystem measurements. The earlier diagnostics' 10m 26s
generation used browser storage and included preparation; these trials do not
establish that browser storage now completes the full job in 2m 09s.

### Remaining work costs

Times below sum card stages; parallel sums overlap and are not elapsed totals.

| Stage | Serial summed seconds | Two-worker summed seconds |
| --- | ---: | ---: |
| First native draw | 53.26 | 69.88 |
| Final native draw | 50.09 | 63.34 |
| PNG encoding | 44.37 | 46.69 |
| Storage save | 35.23 | 42.31 |
| Asset loading | 0.82 | 3.94 |
| Native load and structural scripts | 4.22 | 0.92 |

Drawing is the largest remaining cost. Parallel CPU work also makes individual
draws, encoding and saves slower, while reducing total elapsed time. Increasing
worker count is not automatically beneficial. Removing another native draw pass
would require separate readiness and image comparisons; it is not done here.

## Verification

All 121 PNGs decoded at the expected dimensions and remained in the isolated
workspace. Decoded comparisons were exact for 56 faces. Others have minor browser
image/alpha interpolation differences; every face had less than 0.1% of pixels
with any channel changing by more than four levels. These are not described as
pixel-identical outputs. Side-by-side samples include Class, Saga, land, helper,
token and creature cards.

Tests cover bounded parallel rendering, sequential saves, startup failures,
render failures, storage failures and cancellation during an accepted write.
Native browser structural tests cover 19 faces, including flip, double-sided,
Class, Saga, creature Saga and planeswalker layouts. Static-site checks exercise
real worker scripts, service-worker routing and decoded reference comparisons;
website generation/review/export tests cover both `/` and `/cards/` deployments.

The routine Python gate passed with **909 passed / 4 skipped**. The additional
worker image lease regression passed, as did all 18 browser JavaScript adapter
tests, the 19-face native worker structural test, the static worker reference
test, and all three root/subpath generation, review and ZIP tests.

The compact timing record is [native-worker-benchmark.json](native-worker-benchmark.json).

Reproduction:

```powershell
.venv/Scripts/python.exe scripts/profile_user_deck_render.py
.venv/Scripts/python.exe scripts/benchmark_user_workers.py
.venv/Scripts/python.exe scripts/compare_user_worker_pixels.py
.venv/Scripts/python.exe scripts/profile_native_workers.py
.venv/Scripts/python.exe -m pytest -m routine -q
```

Recovery requires the local source workspace and Supernatural repository assets.
Recovered input descriptions, stage records, pixel metrics and the review sheet
are under ignored `test-results/`. Automatic approval review rejected deletion
of the temporary `test-results/user-deck-workers/{serial,workers,workspace}`
folders with "blocked by policy", so the full-size trial PNGs and copied
benchmark workspace remain there.
