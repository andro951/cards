# Native render experiments

Measured 2026-10-02 with the production static website in normal, headful Chromium and browser storage. Product code is unchanged. Reproduce with `.venv/Scripts/python.exe scripts/profile_native_render.py`.

The profiler builds an isolated website, seeds prepared fixture data, and uses the actual pinned CardConjurer renderer and upstream frame assets. Seven layouts cover a creature, land, Saga, Planeswalker, Station, Godzilla creature, and Prepare card. Each uses Supernatural's original Syr Gwyn artwork, resized to 2010 × 2814, with a different content ID so the baseline cannot reuse one artwork URL for the entire deck. There are two passes per experiment, 84 PNGs total. PNG pixels are compared in all four RGBA channels. Timed rendering includes asset acquisition and PNG encoding; preparation, renderer startup, saving, and evidence collection are excluded.

## Results

Compare cached second passes for speed: the first baseline pass populates the persistent frame cache, whereas subsequent experiments start with that cache available. Average first-pass baseline rendering was **3.185 seconds/card**; its cached second pass was **1.515 seconds/card**.

| Experiment | Cached seconds/card | Exact reference matches | Assessment |
| --- | ---: | ---: | --- |
| Existing pipeline | 1.515 | See baseline issue below | Reference |
| Retain image assets as Blob URLs during the run | 1.361 | 14/14 | About 10% faster; promising |
| Remove the fixed 550ms wait | 1.024 | 12/14 | First-use Saga and Planeswalker differ; reject |
| Skip the first full draw pass | 1.590 | 14/14 | No measured overall improvement |
| Asset retention + no wait + single draw | 0.970 | 13/14 | First-use Planeswalker differs; reject |
| Retain successfully loaded structural scripts | 1.657 | 13/14 | Repeated Planeswalker differs; reject |

Asset retention includes its fetch/Blob creation time. Artwork is reread for each card, while shared frames and set symbols are retained. Embedded data URLs stay unchanged because the renderer's CSP permits image display but does not permit fetching those URLs. Retention is scoped to the isolated renderer lifetime; this is not a new persistent cache or a change to dependency versions.

The existing pipeline's first and second Saga and Planeswalker outputs differ. The Planeswalker difference is substantial: the first output lacks the proper ability panel and shields, while the second contains them. The Saga difference is confined to chapter numerals. Experiments are compared to the fully initialized second baseline pass; the baseline's own recorded comparison flags compare that second pass against the first. This existing initialization issue needs a separate regression and readiness repair before removing waits. Matching the second pass demonstrates comparative correctness for these fixtures, not complete layout coverage.

## Where CardConjurer spends time

In the cached baseline, the explicit first draw averaged 0.042 seconds. Most time is in the fixed wait, loading/setup, PNG encoding, and asset readiness. Replacing CardConjurer's drawing engine is not supported by these results. Its structural script setup and image readiness are better targets, but simply skipping script initialization changes output.

An exploratory headless run was unsuitable for estimating normal app performance: its drawing and callback delays were much longer. Final comparisons above use headful Chromium with the production renderer iframe geometry and sandbox. The profiler supports `--headless` for diagnosis, but those results should not be mixed with this report.

## Frame-cache persistence

A separate storage experiment replayed ten actual upstream frame PNGs, totaling **11,201,122 bytes**, with fixed transport responses. Unique cache URLs and content IDs ensured new writes each time. It isolates storage overhead from internet variability; it does not measure parallel downloading. Three matched repetitions compared ordinary writes with one transactional checkpoint using the existing BrowserStore render-save context.

| Method | Average for ten files | Checkpoints |
| --- | ---: | ---: |
| Individual cache writes | 2.782 seconds | 20 |
| One checkpoint for the group | 2.536 seconds | 1 |

Batching saved about **9%** here. This is an isolated browser workspace with small metadata; selected-folder storage and a larger real workspace database could behave differently. No product cache transaction was changed. `--cache-only` runs this storage experiment separately.

## Next implementation priorities

1. Add explicit first-use readiness checks for Saga and Planeswalker components, with image regressions. Avoid relying on a fixed delay for correctness.
2. Promote scoped asset retention with bounded memory and cancellation cleanup, and expand special-layout coverage before release.
3. Test cache batching against a populated workspace and selected-folder storage before adopting it broadly.
4. After component readiness is verified, retest removing the fixed wait. The roughly half-second saving is meaningful, but the current shortcut is unsafe.

Do not promote unconditional script reuse or a replacement renderer based on these tests. Single-pass drawing provided no meaningful measured benefit in this sample.

Raw measured stages and comparison results are saved in [native-render-profile.json](native-render-profile.json). Generated PNGs and local logs are under `test-results/native-profile/` and are not committed.

## Implementation follow-up — 2026-10-02

The tables above describe the original experiments, before these repairs:

- Saga chapter numerals now load their native `plantinsemibold` font before drawing.
- Planeswalker helper layers are explicitly redrawn after native `loadCard` resizes the canvases. The first render previously lost the ability panel and loyalty shields.
- Class headers now wait for the native header image and redraw their helper canvas. The larger no-wait comparison exposed this additional first-use race.
- Image, font and script readiness replaces the fixed 550 ms per-face settling delay. Both native draw passes and structural script initialization are retained.
- Immutable artwork, frames and masks reuse Blob URLs within the renderer. The cache has a 64 MiB retained-byte limit; a single active face may temporarily exceed it. Release evicts back to the limit, and cancellation/unload aborts outstanding requests and revokes URLs. This limit measures retained compressed assets, not all browser canvas/decoded-image memory.
- Frame and mask cache writes share one transactional metadata checkpoint when a generation session loads a face. Setup and frame choice do not initiate these downloads or rendering. Failed batches roll back and remain retryable.

A populated 121-card browser workspace (about 1.28 MiB of SQLite metadata) gave **5.219 seconds unbatched versus 2.690 seconds batched**, averaged over three alternating ten-frame trials: about **48% less time** in this isolated persistence step. Each batch contained 11,201,122 bytes. This is not a claim of 48% faster overall generation; internet download time was deliberately held constant.

The corresponding real Windows selected-folder run, without other tests running,
averaged **14.442 seconds unbatched versus 8.643 seconds batched**, about **40%
less time**. The selected folder contained the physical 1,314,816-byte SQLite
checkpoint, and all 76 saved HTTP-cache URL/asset-ID pairs survived an actual app
reload. An earlier overlapping test run is excluded from this comparison. See
[populated-workspace cache measurements](frame-cache-profile.json).

`tests/test_native_readiness.py` runs the actual static browser renderer across 22 faces, with two first/repeated passes and a delayed reference. It compares decoded RGBA pixels and fails on any mismatch. Asset lifetime/cancellation and failed-batch rollback/retry checks are routine tests. The renderer pipeline version was bumped so saved images rebuild with these correctness fixes on the next explicit generation.

All 44 no-wait comparisons matched, and the delayed reference's first/repeated outputs also matched. Warm-round render time averaged **1.321 seconds with the old delay versus 0.912 seconds without it** (about 31% lower). This comparison already uses asset retention on both sides, resizes distinct artwork to 1005×1407, and renders 2010×2814 PNGs; it is not directly interchangeable with the earlier seven-layout large-art measurements. See [readiness comparison stages](native-readiness-profile.json).
