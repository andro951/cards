# Native render and PNG save overlap experiment

## Scope and integrity

Benchmark revision: f503693 (before any production overlap change). The harness
builds a temporary static website, runs visible Chromium, and renders seven
prepared structural faces: creature, land, Saga, Planeswalker, Station, Godzilla,
and Prepare. They use the Supernatural deck's Syr Gwyn artwork at 2010 x 2814.
Native CardConjurer drawing and the production PNG persistence API are unchanged.

The measured interval starts after the iframe reports ready and ends after all
seven PNG saves settle. Metadata, preparation, runtime bootstrap, render-plan
lookup and result collection are excluded. These are seven-face pipeline timings,
not whole-deck generation times or a claim about 100-card throughput.

Each storage run has one cold/warmup serial trial and two warm repetitions of
serial, overlap and overlap plus asset prefetch, in balanced order. Overlap permits
only one older PNG save while the next face renders. Prefetch is a temporary test
hook, starts only during explicit generation, and is not shipped in the app.

The first runs reused identical generated assets after warmup. The fresh-save
runs delete generated PNG assets before each trial, outside the measured interval,
while retaining warm artwork/frame caches. This exposes actual new PNG writes
rather than deduplicated saves. Both cases are reported separately.

Every output is compared across all four RGBA channels against its serial
reference. Saved bytes are checked by SHA-256 through the production asset API,
and the last seven saved images are checked again after page reload. Filesystem
runs reuse the already-approved browser session and a child benchmark folder;
they open no native permission picker and restore the original folder preference.

## Measurements

Warm means, seconds for seven faces (two trials per mode):

| Storage and PNG state | Serial | Overlap | Overlap + prefetch |
| --- | ---: | ---: | ---: |
| Browser, existing PNG assets | 11.104 | 10.539 | 10.595 |
| Browser, fresh PNG writes | 11.711 | 11.648 | 11.642 |
| Selected folder, existing PNG assets | 15.527 | 14.655 | 14.521 |
| Selected folder, fresh PNG writes | 19.077 | 20.771 | 18.942 |

All 196 PNGs across the four experiments passed exact RGBA and saved-byte
checks. The last seven outputs in each storage run survived reload with unchanged
bytes. The selected-folder fresh-write prefetch mean is 0.7 percent faster than
serial, while plain overlap is 8.9 percent slower. This is not a reliable gain.

The browser fresh-write difference is less than one percent and inconsistent
between repeats. Existing-asset runs appeared to gain roughly five to six
percent, but they do not represent saving a newly generated deck. Individual
save calls become slower under overlap, showing resource contention.

## Production decision

Keep the current serial render/save sequence. Neither overlap nor experimental
prefetch has demonstrated a reliable improvement for new PNG writes. The cache
and save optimizations already shipped remain intact. Reconsider bounded overlap
only after addressing the measured main-thread work and rerunning fresh-write
trials. The benchmark does not establish a benefit for parallel native renderers.

## Responsiveness finding

The main-page 16 ms timer still records gaps approaching one second during native
rendering. Long-task attribution places the largest pauses inside the CardConjurer
iframe. Several synchronous drawing stages can execute within one browser task,
even when their wrappers are async. Breaking that task at safe boundaries is a
separate experiment; these traces do not prove that changing the renderer or
adding more iframes will help.

## Reproducing

Run `scripts/profile_generation_pipeline.py --fresh-saves` for browser storage.
For a previously approved persistent Chromium session, add `--folder` and, if
needed, `--cdp-url`. The filesystem benchmark refuses to request new permissions.
Full trial measurements are in [generation-pipeline-profile.json](generation-pipeline-profile.json).