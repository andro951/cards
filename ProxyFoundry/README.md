# Bulk Proxy Forge

Bulk Proxy Forge turns public Magic: The Gathering deck links into rendered proxy cards and an explicitly paired front/back ZIP for printing. The production app is a static website: the card engine runs in a browser worker, and the workspace stays on the user's device. The published website needs no local server.

## Use the website

1. Open the deployed website in a current Chrome or Edge browser.
2. Choose **Add New Deck** and paste a public Scryfall deck link, a card list, or a deck export. The optional browser helper can also import public Archidekt and MTGGoldfish links directly on your computer. Without it, download a text or JSON deck export from those sites and upload it. Exact printing details are preserved when the deck source supplies them; otherwise Scryfall chooses its ordinary default result.
3. Choose **Normal Look** for normal MTG artwork and frames, including lands, or **Customize Look** to choose artwork, frames, credits, symbols, backs, and `data.json`. Both choices open Art & Setup. Normal Look starts from ordinary settings even when a custom default style is saved. Other import methods includes an Outside the Game checkbox, enabled by default.
4. Finish setup, save your choices, then press **Generate Images**. No cards are rendered during import, setup, or frame selection. Frame choices use static card-back placeholders until real examples are supplied. After generation, the app reports that the deck is ready. Godzilla land and non-land frames are separate choices. A nickname appears above the real card name.
5. Choose **Review & Print**. Inspect front images and any unique backs. Crop and layout warnings must be reviewed one card at a time; **It Looks Fine** accepts only that face's current render.
6. Build the paired ZIP, then choose **Print Cards**. Without the optional helper, download the ZIP, open TCGPlaytest, and choose **Upload Deck ZIP**. The completion screen shows the exact control. The optional Chrome/Edge helper can send repeat orders automatically. The printer checkout remains in the user's hands.

Saved print packages are available from **Saved print orders** on the Deck Library page.

The first load downloads the pinned card engine and renderer assets. Rendering, imported art, templates, decks, and saved orders can use substantial browser storage. **Settings → Workspace storage** lets supported browsers use a chosen `BulkProxyForge` folder; browser-managed storage is the default. A remembered folder requires explicit reconnection when its permission expires; opening a separate browser workspace is an explicit choice. **Export Backup** and **Import from Backup** move selected objects and source assets between workspaces. A backup can optionally include generated images.

## Preview the checked-out website on Windows

Double-click `START_BULK_PROXY_FORGE.bat` in the `ProxyFoundry` folder. It builds the static site, opens `http://127.0.0.1:8767/` in your browser, and shows a small **Local Preview** window. Keep that window open while using the site; choose **Stop preview** when finished. You do not need to type commands or install Node.js. Python 3.10 or newer is required to start this local preview. You can also double-click `START_BULK_PROXY_FORGE.pyw` directly. `START_PROXY_FOUNDRY.bat` continues to open the original Python app.

This temporary local HTTP server serves only the site's files to your own computer. The card engine, saved decks, and images still run and live in your browser. The fixed address keeps browser storage tied to the same origin between preview sessions. The published website will not require this launcher.

## Host the website

The production app is static. There is no server function or account database. Card rendering and saved decks run in the browser. Scryfall and GitHub data are fetched directly by the browser. Archidekt and MTGGoldfish block direct cross-origin browser reads, so their link imports use the optional Chrome/Edge helper installed on each user's machine. File exports work without the helper.

```powershell
cd ProxyFoundry
python scripts/build_web.py
```

Publish the generated `dist` directory on a static host. Use `python scripts/build_web.py --base-path /cards/` for a repository path, or `--github-pages` to derive the path from the repository. The manual **Publish Bulk Proxy Forge website** GitHub Action builds and publishes `dist`; see [browser storage and hosting](docs/BROWSER_WEBSITE.md). The double-click launcher uses a local HTTP server for previews, and tests can use one too. No local server is part of the published website.

The optional browser helper recognizes `andro951.github.io`, Cloudflare `*.pages.dev` sites, and localhost development builds. Its permissions also cover the two deck sites and TCGPlaytest. Its permission list must be updated for a custom domain. The helper is not needed to download a print ZIP or upload deck exports.

## Artwork and templates

The four bundled rarity symbols and Bulk Proxy Forge back are selected automatically. Custom setup can use a public GitHub art folder or a computer art folder. Missing custom art is an error by default; the user can explicitly enable Scryfall fallback. Set symbols can be replaced individually, from a four-image computer folder, or from a four-image public GitHub folder. The one-click GitHub project import keeps its existing folder format; see [GitHub setup import](docs/GITHUB_SETUP_IMPORT.md).

Artwork filenames can include a numeric export prefix: `001_command_tower.png` matches Command Tower. Matching also tolerates separator differences such as `commandtower.png`. Exact normalized names take priority. If several files match, choose an artwork override or rename one to the exact card name; the app does not guess between them.

`data.json` can be chosen locally, linked directly on GitHub, or discovered in a one-click GitHub project folder. Its version-1 card entries support `nickname`, `flavor_text`, and `artist`. Custom artwork requires a credit for each image, supplied by a deck-wide artist, per-card artist entry, or `data.json`. Selected Scryfall art retains the printing's artist credit.

Templates use a versioned reusable model with semantic text regions, native structural slots, geometry formulas, and conditional frame variants. [Template model v3](docs/TEMPLATE_MODEL.md) documents the format and its compatibility checks. The Templates area creates them from built-ins or converts a CardConjurer save, validates compatibility, and imports/exports portable template JSON. Uploaded frame images travel with a template export. A template in use by a saved deck cannot be deleted until the dependency is removed.

Token frame choices include **Classic arched**, **Modern full-art**, and **Modern borderless**. Automatic tokens use the classic arched frame. Classic and modern full-art styles use a larger art window for empty text or a short plain keyword, and a rules box for longer abilities or flavor text. Borderless tokens place outlined text over the art. These choices also work with deck-wide token conversion. The complete upstream frame images are used; only dual-color pinline accents use a separate mask.

The renderer uses the pinned Card Tools v58 source and native CardConjurer runtime. Special layouts are routed to their appropriate renderer. Unsupported structures fail with a clear preparation error instead of receiving an ordinary frame. Finished PNGs are cached by render inputs; saved print orders are immutable snapshots with matching `FRONT/000001.png` and `BACK/000001.png` names for each physical card.

## Development and tests

Install development dependencies from `requirements-dev.txt`, then build the site and run the routine group:

```powershell
python -m pip install -r requirements-dev.txt
python scripts/verify_vendor.py
python scripts/build_web.py
python -m pytest -q -m routine
node --test tests_web/*.test.mjs
```

`RUN_TESTS.bat` runs routine, extended, or complete groups. CI runs the routine group plus focused static-browser production, progress/cancellation, and response-integrity checks. The extended group includes native rendering, the installed print helper, live dependencies, and large-order stress tests. See [test groups and measured timings](docs/TESTING.md). Tests never check out or enter payment information on TCGPlaytest.

The original Python app remains available through `START_PROXY_FOUNDRY.bat` and `run.py`.
