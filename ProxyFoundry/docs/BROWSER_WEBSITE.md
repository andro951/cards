# Browser workspace and website hosting

## Using the checked-out website

Double-click `START_BULK_PROXY_FORGE.bat`. The Local Preview window serves static files at the fixed localhost address. The engine and workspace run in the browser. The old `START_PROXY_FOUNDRY.bat` continues to open the old app.

Both Normal Look and Customize Look lead to Art & Setup. Importing resolves card metadata, which can take time and now shows progress and a Cancel control. It does not download artwork or render cards. Frame pickers and CardConjurer source choices use static card-back samples. Explicit template-validation buttons render only the samples requested there. Deck rendering starts at Generate Images.

## Storage and recovery

The browser stores workspace metadata in SQLite snapshots and binary assets directly in browser-managed files. Selected workspace folders use the same file layout. Binary artwork, renderer assets, PNGs, and ZIPs are not mirrored into Python's memory filesystem. The active image and compiler scratch buffers still use memory while processing.

Each metadata mutation commits a durable SQLite snapshot. Preparation checkpoints after each card; completed PNGs are saved individually. Reloading interrupts active work and reports that interruption. Generate Images reuses matching completed PNGs. Editing keeps the previous image visible until a replacement is generated; it does not mark that image as current.

Only one writer tab can open a workspace on an origin at a time. Close the first tab to use another. Expired folder permission shows Reconnect workspace folder. Opening the separate browser-managed workspace requires an explicit choice and leaves folder data where it is.

Browser storage belongs to the site's origin. Localhost and a published GitHub Pages site have separate storage. Export Backup/Import from Backup transfers decks, templates and source assets; optionally include finished images. Changing browser profiles also changes browser-managed storage.

Browser diagnostics remain downloadable if the engine fails, and include the previous session's recorded events. Storage quota and permission failures are reported. Available disk/browser quota still limits workspace size. Use Settings backups for recovery and transfers.

## Deleting decks and saved print orders

Deleting a deck checks saved print orders first. An order referencing the deck blocks deletion and offers **Show print orders**, opening an order list filtered by that deck's ID. **Show all print orders** clears the filter. Each saved order has Review and Delete print order controls. Deleting an order removes its saved ZIP and preview; it keeps the decks.

After confirming an unblocked deck deletion, its tile disappears and the Deck Library opens immediately. The metadata deletion and saved-file cleanup continue in the background. A pending request survives reload and is scoped to the workspace. Failed metadata deletion restores the tile and reports the error. Cleanup runs in small batches, preserves referenced/shared assets, and resumes after reload. A cleanup failure offers Retry cleanup. Wait for active image generation to finish before deleting its deck.

## GitHub Pages without console commands

1. In the repository's Settings → Pages, choose GitHub Actions as the source.
2. In Actions, open **Publish Bulk Proxy Forge website** and click Run workflow on main.
3. The deployment's environment link opens the published site. The workflow is manual; ordinary commits do not deploy automatically.

The workflow uploads only the static `ProxyFoundry/dist` output. No hosted Python process, function, database, or Cloudflare service is used. Renderer assets and card metadata are fetched by the browser; cross-origin deck sites use the optional local browser extension or exported deck files.

A project build supports `/cards/`. A user/organization `*.github.io` repository uses `/`. Developers can also pass another base path ending with a slash. The actual Chromium smoke test covers import, setup, generation, review, paired ZIP export and reload under `/cards/`.
