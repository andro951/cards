# Slow-operation timing logs

Operations taking at least 0.1 seconds write a `TIMING` JSON entry to the rotating workspace `logs/app.log`, included in Settings → Download Diagnostics. Browser render totals also appear in the browser diagnostics JSON. Use a newly loaded website to capture a new run; older sessions do not have this instrumentation.

Each new entry includes `storageType`: `browser` for browser-managed storage, `selected-folder` for a user-selected computer folder, or `local-folder` for the old local application. The diagnostics summary also includes `workspace.storageType`; earlier log entries are not backfilled.

Each entry identifies the stage, elapsed seconds and outcome, plus the available card name, URL, render key, asset byte count or cache status. Failures retain their original behavior. Logging failures do not fail the operation. The 0.1-second threshold suppresses fast operations; an absent entry does not mean the operation was skipped.

## Stages

- `network.fetch` / `network.transient`: complete request including cache read or download and persistence; cache and byte count appear on successful requests.
- `network.download`: transport duration, including browser fetch and body transfer.
- `network.attempt`, `network.retry-wait`: individual local transport attempts and retry backoff; the browser transport currently has no automatic retry loop.
- `network.rate-wait`: Scryfall throttle delay.
- `scryfall.resolve` / `scryfall.flavor`: metadata and flavor selection.
- `deck.import`, `github.index`, `deck.prepare`, `card.prepare`, `art.resolve`, `card.compile`: import, folder listing, per-deck/per-card preparation, artwork acquisition and compiled frame/card data.
- `image.decode`, `image.encode-png`: decoding and PNG conversion for ordinary image imports; native rendered PNGs bypass re-encoding.
- `render.validate-png`, `render.persist`: native PNG verification/decode and complete engine-side persistence.
- `storage.asset`, `storage.document`, `storage.render`, `storage.checkpoint`: asset and metadata writes, saved render registration, SQLite snapshot/persistence.
- `api.request`: browser engine request processing, including slow export/ZIP operations. It excludes message queue time.
- `runtime.prepare`, `runtime.start`: renderer dependency preparation and startup.
- `render.load-face`, `render.native`, `render.save`, `render.total`: loading compiled data, native rendering, saving PNG and render-plan total.
- `native.assets`, `native.fonts`, `native.symbols`, `native.load-and-scripts`, `native.loaded-images`, `native.loaded-fonts`, `native.first-draw`, `native.settle-wait`, `native.final-draw`, `native.png-export`: renderer substeps. The settle wait is the existing 550ms delay, now visible in timings.

Start with the longest entries and inspect their nested stages to distinguish network, storage, compilation and rendering costs. Timings are inclusive: for example, card.prepare includes art.resolve and card.compile; do not add every entry together. Rendering diagnostics retain their existing details to explain which assets/frame were being processed. No new server or analytics service is used.

Verification covers the threshold, original exception/result behavior, logger failure isolation, cache versus download and byte counts, and actual static browser rendering with timing entries in the downloaded diagnostics ZIP.
