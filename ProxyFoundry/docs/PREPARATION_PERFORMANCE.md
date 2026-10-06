# Preparation caching and measurements

## Unchanged-deck planning (2026-10-06)

Preparation now builds a change plan before processing cards. The GitHub folder
commit check still runs; cache metadata is read in batches, and shared asset
files are checked once. Only cards with changed inputs, expired preparation, or
missing required files enter the preparation loop. Render planning continues to
queue only missing or changed output images.

An unchanged prepared deck produces one preparation summary, performs no deck
saves, and keeps its revision. Preparation completion logs only changed faces.
The static browser job returns ID/revision/status/summary rather than serializing
the whole compiled deck into its durable job log; the UI already reloads the
deck separately. Full deck results remain available through the workspace and
local HTTP API.

The real Chromium/OPFS regression measured **0.6693 seconds** after browser reload
for a synthetic deck of 121 prepared faces with shared artwork, zero card work,
zero deck saves, one progress event, and a 169-byte result. This is an isolated
planning/completion measurement, not a benchmark of the user's selected-folder
workspace or its GitHub round trip. Evidence is in the ignored
`test-results/unchanged-preparation-browser.json`.

Regression coverage checks unchanged runs without processing/saves, selective
nickname changes, GitHub changes, missing assets, freshness, cancellation,
conflict protection, and the browser reload/compact-result path.

## Earlier live-source measurements

Measured 2026-10-06 against live sources on this computer. These are individual
runs, not averages or a comparison with the previous application version.
The card is real Fighter Class, AFR 222. No renderer was invoked and every run
had zero generated/review images. Existing setup/default symbols and deck creation
were completed before timing began; the first run's card metadata and artwork
were cold. Each source used its own isolated workspace.

## Changes

- Preserve original PNG/JPEG/WebP bytes unless orientation correction or a crop
  requires new pixels. Finished card output remains PNG. Original WebP dimensions
  are supported in Card Tools fitting.
- Persist GitHub folder indexes by repository, folder, branch, and commit. An
  unchanged commit skips the directory listing. For changed commits, compare the
  commits and retain old immutable URLs for unchanged paths. Added, changed,
  removed, and renamed files are handled using GitHub's response. Unavailable,
  diverged, or capped comparisons conservatively refresh source URLs.
- Remove per-file Git blob hash verification. Content-addressed storage still
  computes its asset identity on initial ingestion; cached preparation does not
  reread/hash artwork files.
- Persist source/transform-to-asset mappings, including the approved Scryfall
  Saga-creature crop. Reuse processed artwork after restarts and after text/style
  changes. Missing assets are reacquired. Existing Scryfall cache expiration and
  refresh intervals continue to apply.
- Persist preparation input fingerprints. Unchanged cards skip metadata
  resolution, artwork acquisition, and frame compilation. Settings, artwork,
  card metadata, face overrides, and template identities affect reuse. Display
  fields, generated results, and warning acknowledgments do not.
- Use local symbol paths during geometry computation and asset URLs in compiled
  cards, avoiding temporary base64 copies of artwork and symbols.
- Batch deck writes after ten cards or two seconds. Retain cooperative yields
  between cards, flush staged progress on cancellation/interruption, and reject
  stale revisions rather than overwriting another edit.
- Persist bundled-symbol preprocessing and remove a redundant deck read.

Older prepared decks need one preparation pass to populate the new cache.

## Results

| Artwork source | New card | Cached card | Cached after restart |
| --- | ---: | ---: | ---: |
| GitHub supernatural/art | 2.2213 s | 0.2786 s | 0.3839 s |
| Scryfall printing artwork | 0.7171 s | 0.0696 s | 0.1704 s |

### GitHub preparation stages

| Stage | New card | Cached card |
| --- | ---: | ---: |
| Load saved deck | 0.0078 s | 0.0083 s |
| Validate setup | 0.0182 s | 0.0155 s |
| Resolve GitHub commit/folder | 1.2135 s | 0.2046 s |
| Check prepared inputs/assets | 0.0002 s | 0.0187 s |
| Resolve card metadata | 0.2443 s | skipped |
| Acquire/validate artwork | 0.6482 s | skipped |
| Compile frame/card data | 0.0596 s | skipped |
| Save prepared deck | 0.0147 s | 0.0192 s |
| Load final result | 0.0068 s | 0.0061 s |

Artwork acquisition includes downloading, validating, and persisting the image.
Its image decoding substage took 0.1194 seconds. No PNG encoding occurred.
The longest individual cold GitHub request was the directory listing (0.6402 s),
followed by the branch lookup (0.4692 s) and artwork download (0.4241 s).
Other nested timings are inclusive and must not be added to their parent stages.

The longest cold GitHub phase was resolving its commit and directory. The cached
GitHub run's longest phase was its live branch-head check: one API request for
the entire folder, with no artwork or card-metadata download. Scryfall cold
artwork acquisition was 0.3798 seconds, metadata 0.2303 seconds, and compilation
0.0535 seconds. Cached Scryfall preparation made zero network requests; its
largest individual phase was input/asset verification at 0.0217 seconds.
Cached runs after restarting also did no compilation or card-art decoding. Setup validation was approximately 0.10 seconds
after restarting, including the existing built-in back validation.

## Remaining opportunities

1. Overlap independent GitHub inventory and Scryfall metadata requests, or begin
   those metadata-only checks while the user chooses setup options. Cold network
   round trips now outweigh compilation and image validation.
2. Reduce repeated SQLite connections during cache verification by reading asset
   existence/dimensions in batches. This matters more for full decks than for one
   card; a full-deck timing run is needed before estimating the gain.
3. Reuse verified built-in back metadata across restarts, with invalidation when
   its packaged manifest/file changes. The remaining restart setup overhead is
   around a tenth of a second in these runs.

The live GitHub branch check remains intentional so updated repository artwork
is recognized. Caching it briefly would reduce repeated requests but introduce
an interval during which new commits are not noticed.

## Verification and reproduction

- Normal suite: `python -m pytest -q -m routine` — 897 passed, 4 skipped,
  158 extended cases deselected, 512.18 seconds.
- New coverage includes byte/format preservation, transforms, durable indexes,
  comparisons and safe fallbacks, additions/removals/renames, selective card
  invalidation, restart reuse, missing artwork, and cancellation batching.
- Existing frame version assertions were updated to the current recipes; no
  frame geometry changed in this performance pass.
- Static browser distribution rebuilt with `scripts/build_web.py`.
- With `PYTHONPATH` set to the app directory, run
  `scripts/benchmark_preparation.py --source github` or `--source scryfall`.
  `--output` chooses the JSON report. The benchmark checks that cached runs do
  not compile or decode artwork and that no output images are rendered.
- Raw stage logs from this run are in the ignored `test-results` folder:
  `preparation-timing-github.json`, `preparation-timing-scryfall.json`, and
  `routine-preparation-final.txt`.
