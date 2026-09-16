# Bulk Proxy Forge

A local-first workspace for turning multiple MTG decks into one explicitly paired print order. Built around the approved Card Tools v58 compiler and CardConjurer's actual native renderer.

## Start here

1. Extract the complete ZIP into a permanent folder.
2. Double-click **START_BULK_PROXY_FORGE.bat**. Python 3.10 or newer is required. The launcher creates a private `.venv` and installs Pillow when needed.
3. The workspace opens automatically in your browser. Keep the launcher window open.
4. Click **Import deck** and paste a public Scryfall deck URL, JSON export, or card list.
5. In **Art & setup**, choose original printing art, a GitHub folder, or a computer folder. Select templates, supply four rarity symbols (or generate four treatments from one), and choose a deck back.
6. Click **Save & generate images**. Completed cards appear in the grid and are cached locally.
7. Select one or more decks, choose **Review print order**, check both sides and any crop/layout warnings, and build the paired ZIP.
8. Save the images ZIP or use **Open in TCGPlaytest**. The printer opens in a **new tab**; Bulk Proxy Forge stays open. Review the printer proof and complete checkout yourself.

**Do not double-click `site/index.html`.** Bulk Proxy Forge uses the local server started by the BAT. Normal use requires no Git, Node, Playwright or full CardConjurer repository download.

On macOS/Linux: install `requirements.txt` in a Python environment and run `python run.py`. `python run.py --no-browser --port 8765` starts without opening a tab.

## Printer helper: one-time setup

The app imports, prepares, renders and exports without an extension. The helper is needed only to fill TCGPlaytest's editor automatically.

Remove the old test helper. Open `edge://extensions` or `chrome://extensions`, enable Developer mode, and choose **Load unpacked → extension/** from this package. Reload the app; the top-right indicator should say **connected**. The app's helper setup dialog also offers a small standalone helper ZIP. No file-URL permission toggle is needed.

The helper asks **Add** or **Replace** when the printer already contains cards. Replace confirms recognized deletion dialogs and checks the count decreases. An unfamiliar flow stops before upload. The overlay can be minimized or closed and closes automatically after success. The helper does not enter payment details or click Checkout.

ZIP transfers through the browser helper are limited to **1 GB**. Larger packages can be downloaded for manual upload or split into smaller orders. The implemented printer integration is **TCGPlaytest**, not every service named MTGProxy.

## Deck and artwork management

Manage independent decks, duplicates, editable names and notes, quantities, bulk additions, removal, trash and restore. Scryfall deck exports and set/collector-number lists preserve exact printings. The inspector can select a different printing or override a face's artwork, credit, template, rarity, rules/flavor text and artwork placement.

Artwork source choices are deliberately separate:

- **Scryfall printing** uses the illustration from the chosen printing.
- **GitHub folder** accepts an explicit public folder URL, without a local repository path.
- **Computer folder** copies chosen images into the local workspace; it does not upload them to GitHub.

Name matching normalizes to lowercase underscores, removes apostrophes and strips accents. Duplicate normalized filenames are reported rather than selected arbitrarily. Missing custom art can fall back to the original printing when that option is enabled.

The optional full-art land library is **unset by default**. Add its GitHub folder in Settings and enable it for a deck. It expects `card_name.png`. Individual art overrides and the main custom-art folder take priority.

Artist credits are source-aware. Actual Scryfall artwork, including fallback images, always uses the selected printing's real artist (face-specific when provided). A custom-art deck default or per-card override cannot overwrite or hide that original credit. Missing Scryfall metadata stays blank rather than being attributed to the custom-art artist.

For custom artwork, use a deck-wide artist or edit each card's credit. **Use the original printing artist for this custom image** keeps the original attribution when you upload modified/extended artwork. Add optional **Modification credit** such as `Modified by ChatGPT` in the deck setup or card inspector. It displays in the normal artist spot as `Artist Name · Modified by ChatGPT`. A per-face value replaces the deck suffix; **No modification credit on this face** suppresses it. Both screens preview the complete artist line before generation. The stored Scryfall artist is never modified, and regenerating does not duplicate the suffix.

Four rarity symbols are required before generation. Upload all four or explicitly generate common/uncommon/rare/mythic color treatments from one image. Review those previews: they preserve transparency but do not redraw the original symbol. PNG/JPEG/WebP/GIF images and sanitized SVG symbols are accepted.

## Updating from the previous test build

This release uses the supplied **Card Tools v58**, with the existing source-aware artist/modification controls retained. Existing decks prepared with the old generator are marked as needing generation. Generate them once to apply native Station rendering and the updated Flip spacing; their previously saved PNGs and order ZIPs are not deleted. Future back-only and quantity-only changes still reuse front renders.

The print helper is **unchanged from version 1.0.0**. An already connected 1.0.0 helper does not need replacement for this update. Earlier 0.9.x test helpers still need the integrated helper setup described above.

The previous v48-to-v54 comparison remains in `docs/CARD_TOOLS_V54_REVIEW.md`. This update follows the supplied v54-to-v58 handoff; see `docs/CARD_TOOLS_V58_UPDATE.md`. `docs/CARD_TOOLS_V58_MANIFEST.json` records exact hashes for all ten supplied source/document files.

## Templates and accuracy

**Automatic** delegates to the original v58 recipe builder. Its source, frame geometry, masking and typography are not rewritten. The original source files are guarded by `scripts/verify_vendor.py`.

For ordinary layouts, **Classic card** and **Crowned full art** support legendary/nonlegendary cards; **Full-art land** supports nonlegendary cards only because its frame has no compatible crown. Creature overrides retain a power/toughness box.

Special structural layouts are identified separately. A layout without an approved recipe requires an explicitly compatible custom template instead of an incorrect ordinary frame. The approved built-in modal-DFC pair is **Esika / The Prismatic Bridge**; its hardcoded reminder-strip treatment is not reused for unrelated modal DFCs. Other modal or transform pairs, split/Adventure/Room cards and unsupported structures require suitable custom templates. Kamigawa Flip cards now use the native v58 single-card recipe with a rotated lower face and ordinary deck back; they are not DFC reverses.

Create a separate custom style from a protected built-in copy, or upload a `.cardconjurer` face. Map its named text boxes to card fields and select the groups it supports. The advanced editor exposes native template JSON. Editing or deleting a custom template invalidates only dependent decks; existing order snapshots do not change.

Review an example of a new style before ordering. Generic text-slot mapping cannot invent missing second-face rules boxes or infer every custom layout. No AI image generation is used.

## Native Station support in 1.2

Spacecraft use the supplied v58 `station` recipe with the ordinary artifact body underneath, color-correct Station pinline above the Station overlay, and native three-section rules, threshold badges and Station P/T. One/two-threshold parsing retains continuation lines in the correct tier. Unsupported structures fail instead of being flattened into ordinary artifact rules. Flip cards retain an additional 2% of card width around their visible P/T medallions.

The existing pinned GitHub core predates Station. For Stations only, the app additionally fetches the genuine `https://cardconjurer.app/js/frames/versionStation.js` module, pinned by SHA-256 `481c2be522fc10089e75aa6281aace9e88e345868330948dd64705edb9314c21`. It is fetched individually and cached, not bundled or re-created. A different upstream version is rejected rather than executed silently. Station images come from the existing pinned GitHub asset source. The adapter replaces one UI `eval` assignment with an equivalent checked property assignment and composites the native Station canvases in the same order as the newer core. Native drawing and layout are unchanged.

## Rendering and ordering

The app fetches individual code/assets from pinned CardConjurer commits and runs native `loadCard()` / `cardCanvas` rendering in a separate-origin local frame. The full upstream repository archive and thumbnail catalogue are never downloaded. Only completed, correctly sized PNGs enter the render cache.

The grid stays on the Bulk Proxy Forge page. Cancelled/failed runs retain completed images. Changing a back or quantity does not redraw unchanged fronts. Crop warnings appear when more than 20% of image width or height lies outside the chosen art window.

Every physical card has explicit matching filenames, for example `FRONT/000001.png` and `BACK/000001.png`. Real reverse faces, deck-default backs, individual overrides and quantities are included. Multiple selected decks become one order ZIP. Saved order packages are immutable snapshots and do not change when a deck is later edited.

## Storage, cache and backups

New Windows workspaces use `%LOCALAPPDATA%\BulkProxyForge`; macOS/Linux use `~/.local/share/BulkProxyForge` or `$XDG_DATA_HOME/BulkProxyForge`. Existing `ProxyFoundry` workspaces continue in place automatically so the rename never strands saved decks. Set `BULK_PROXY_FORGE_HOME` to choose another location; the old `PROXY_FOUNDRY_HOME` override remains accepted for compatibility.

Replacing the extracted app folder does not remove the workspace. Do not delete that workspace directory unless you intend to erase its saved data.

Scryfall data/art cache is **365 days**, or **7 days** with Fetch new data enabled. Fresh entries are reused, not fetched on every request. Mutable custom GitHub art is rechecked after ten minutes or immediately with **Refresh custom GitHub art**; that is separate from the Scryfall policy. Pinned CardConjurer dependencies are cached individually.

SQLite transactions and revision checks prevent two tabs from silently overwriting deck edits. Portable backups include decks, custom templates, referenced images and completed renders, excluding runtime/font/HTTP caches, browser credentials and printer transfer secrets. Restore adds copies rather than overwriting existing decks. Export a backup before moving computers or deleting the workspace.

## Original Card Tools and tests

Original-printing PNG download and copy-token utilities are available under **Quick start & Card Tools**. The complete original interface and command-line tools remain under `vendor/card_tools`. Double-click **START_LEGACY_CARD_TOOLS.bat** for advanced original workflows using the same private Python environment.

Double-click **RUN_TESTS.bat** for core tests or optional full Chromium/native-render tests. Development setup:

```
python -m pip install -r requirements-dev.txt
python scripts/verify_vendor.py
python -m pytest -q
python -m playwright install chromium
```

Set `PF_BROWSER=1` and `PF_LIVE_CC=1` for real HTTP/browser and pinned upstream-render tests. The optional `PF_DOM=1` component tests use a controlled about:blank DOM. CI distinguishes these from real browser navigation and native rendering. The installed-extension test loads the actual MV3 extension but intercepts the merchant page with a controlled editor fixture. No tests place a real order or pay.

The release ZIP includes source, launchers, tests and a SHA-256 file manifest. Runtime caches, font files and keys are excluded. Source/checkpoints are stored in `andro951/cards/ProxyFoundry`.

## Troubleshooting and scope

Keep the launcher open until rendering or printer transfer finishes. Fix the reported face/source/template and retry; completed images remain saved. Settings → **Download diagnostics ZIP** records recent errors and dependency paths. Review it before sharing because card names and public URLs may appear. Browser storage and printer authorization tokens are omitted.

The Windows launcher is supplied for local use; automated browser runs use Linux Chromium. The live merchant's current UI and actual Windows installation remain distinct from CI's controlled printer fixture. Use the paired ZIP manually if the merchant changes its editor. Always review the printer proof: correct PNGs do not certify bleed settings, paper choice or manufacturing alignment.
