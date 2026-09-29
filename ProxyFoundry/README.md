# Bulk Proxy Forge

Bulk Proxy Forge turns public Magic: The Gathering deck links into rendered proxy cards and an explicitly paired front/back ZIP for printing. The production app is a static website: the card engine runs in a browser worker, and the workspace stays on the user's device. Users do not start a local server.

## Use the website

1. Open the deployed website in a current Chrome or Edge browser.
2. Choose **Add New Deck** and paste a public Scryfall, Archidekt, or MTGGoldfish deck link. Outside-the-Game cards are included by default and can be excluded before import. Exact printing details are preserved when the deck source supplies them; otherwise Scryfall chooses its ordinary default result.
3. Choose **Default Look** for automatic art, frames, symbols, and back, or **Custom** for artwork folders, frames, credits, symbols, backs, and `data.json`.
4. Generate images. Select a frame by inspecting actual rendered previews for a card from the deck. Godzilla land and non-land frames are separate choices. A nickname appears above the real card name.
5. Choose **Review & Print**. Inspect front images and any unique backs. Crop and layout warnings must be reviewed one card at a time; **It Looks Fine** accepts only that face's current render.
6. Build the paired ZIP, then choose **Print Cards**. Without the optional helper, download the ZIP, open TCGPlaytest, and choose **Upload Deck ZIP**. The completion screen shows the exact control. The optional Chrome/Edge helper can send repeat orders automatically. The printer checkout remains in the user's hands.

Saved print packages are available from **Saved print orders** on the Deck Library page.

The first load downloads the pinned card engine and renderer assets. Rendering, imported art, templates, decks, and saved orders can use substantial browser storage. **Settings → Workspace storage** lets supported browsers use a chosen `BulkProxyForge` folder; browser storage is the fallback. **Export Backup** and **Import from Backup** move selected objects and source assets between workspaces. A backup can optionally include generated images.

## Deploy the website

The static site uses Cloudflare Pages. Its only server function is a stateless deck-site gateway for public Archidekt and MTGGoldfish pages whose browser CORS behavior prevents direct import. It stores no deck, image, or workspace data. Scryfall and GitHub data are fetched by the browser.

```powershell
cd ProxyFoundry
python scripts/build_web.py
npx wrangler pages deploy dist --project-name bulk-proxy-forge
```

Configure Cloudflare Pages to serve the `dist` directory. The build includes `functions/gateway/deck.js` as the stateless gateway; deploy from the repository root if the Pages tool requires the `functions` directory beside `dist`. For local development and browser testing only, `npx wrangler pages dev dist --port 8767` serves the same website. No local server is part of the delivered product.

The optional print helper currently recognizes Cloudflare `*.pages.dev` sites and localhost development builds. Its permission list can be extended when a custom domain is assigned. The helper is not needed to download a print ZIP.

## Artwork and templates

The four bundled rarity symbols and Bulk Proxy Forge back are selected automatically. Custom setup can use a public GitHub art folder or a computer art folder. Missing custom art is an error by default; the user can explicitly enable Scryfall fallback. Set symbols can be replaced individually, from a four-image computer folder, or from a four-image public GitHub folder. The one-click GitHub project import keeps its existing folder format; see [GitHub setup import](docs/GITHUB_SETUP_IMPORT.md).

`data.json` can be chosen locally, linked directly on GitHub, or discovered in a one-click GitHub project folder. Its version-1 card entries support `nickname`, `flavor_text`, and `artist`. Custom artwork requires a credit for each image, supplied by a deck-wide artist, per-card artist entry, or `data.json`. Selected Scryfall art retains the printing's artist credit.

Templates are reusable, versioned objects with semantic text regions. The Templates area creates them from built-ins or converts a CardConjurer save, validates compatibility, and imports/exports portable template JSON. Uploaded frame images travel with a template export. A template in use by a saved deck cannot be deleted until the dependency is removed.

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

`RUN_TESTS.bat` runs routine, extended, or complete groups. The extended group includes native rendering, browser website smoke, the installed print helper, live dependencies, and large-order stress tests. See [test groups and measured timings](docs/TESTING.md). Tests never check out or enter payment information on TCGPlaytest.

The old Python launcher and `vendor/card_tools` remain in the repository for development and legacy workflows. The website does not ask users to run either.
