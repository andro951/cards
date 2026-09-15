# Proxy Foundry 1.2 — Card Tools v58 update

## Basis and preservation

This update follows the supplied v54-to-v58 handoff in `Pasted markdown(20260915-223823).md` and the actual `MTG_Card_Pipeline_Local_UI_v58(1).zip` package. Automated byte comparison confirms that the only changed distributed source/document file versus v54 is `pipeline/card_data_to_cardconjurer.py`; all nine other files are unchanged. Generated Python bytecode is not treated as source.

All ten vendor source/document files match the uploaded v58 package byte-for-byte. `CARD_TOOLS_V58_MANIFEST.json` records their hashes. The source-aware artist-credit resolver, artist UI module, and all four printer-helper files remain byte-identical to Proxy Foundry 1.1. No new template math is substituted for the supplied compiler.

## Incorporated changes

### Flip medallion clearance

The v58 compiler reserves the additional 0.0200 card-width visual overhang beside each Flip P/T medallion. The upright set symbol is shifted left of that protected edge and normal gap; the rotated lower type text reserves equivalent clearance on its side. Budoka/Dokai remains one physical card with the deck's ordinary back.

### Native Station recipe and parsing

Spacecraft route to the dedicated `station` recipe and must also be artifacts. The recipe begins with the approved ordinary artifact body, then applies the Station overlay and native Station state. Its `ability0`, `ability1`, `ability2`, and `pt` fields are not flattened into one generic rules textbox.

Threshold continuation lines stay with their threshold until another threshold begins. One threshold with ordinary pre-Station text retains three meaningful regions; a single threshold without pre-text uses the compact option. Two thresholds receive separate regions and badges. Unsupported threshold counts or invalid structures raise explicit errors.

The obsolete homemade SVG badge and approximate line-count placement systems are not used. The native Station module draws the badge and its own P/T medallion; no ordinary M15 P/T frame is added.

### Calibrated badges and colored pinlines

The supplied state retains 151.2 × 151.2 badge dimensions, x = -88 and y = 3, with full-opacity badge drawing. Translucent ability-region backgrounds remain separate. Crown layers, when present, stay above the colored Station pinline, full Station overlay, and underlying ordinary artifact body.

The visible Pinline-masked layer uses artifact treatment for colorless cards, the card color for monocolor, the approved eased gradient for two colors, and gold for three or more colors. These are the supplied policies, not new colors invented by Proxy Foundry.

Landscape Station images retain the supplied 156/2010 horizontal position, 320/2814 vertical position, and 2.73 zoom rather than generic autofitting. Portrait images retain the existing autofit path. Explicit user art-placement overrides still take precedence when chosen.

## Native renderer integration

The existing pinned GitHub CardConjurer core predates Station support. Stations additionally load the actual `versionStation.js` module from `https://cardconjurer.app/js/frames/versionStation.js`, individually and on demand. Its verified SHA-256 is `481c2be522fc10089e75aa6281aace9e88e345868330948dd64705edb9314c21`. A changed module is rejected rather than executed silently. Only this exact site URL is allowed; Station image files use the existing pinned GitHub asset source.

The adapter replaces the native module's one UI eval-based property assignment with a checked equivalent and composes the two native Station canvases at the required point in the older core's draw order. It does not redraw badges, P/T, frames, or Station text itself. Stale Station callbacks are cleared when moving to another card. The full repository and font files are not bundled in the release.

## Verification

The tested runtime revision `92e72f3ed2eb4962e0a9ff3ae506105d1d0ff2e9` passed the full enabled browser/native-render suite in GitHub Actions run `35033784334`: **151 passed, zero failures or errors, two optional offline-only tests skipped** (153 cases, 297.871 seconds).

The Station test rendered four Station variants and a normal creature between them, using genuine CardConjurer code/assets with synthetic test artwork and text. It verified native image draw calls: badge dimensions 151.2 × 151.2 at alpha 1; P/T dimensions 306 × 148 at alpha 1; preserved badge values; correct compact/three-region behavior; and five explicit front/back ZIP pairs. Exported images were inspected for region placement, pinline colors, badges, P/T and artist text.

The existing real-browser, artist-credit, eleven-face structural, Scryfall caching, custom-template and installed-extension transfer tests also passed. The merchant page in the extension test is a controlled editor fixture; no live order, payment or checkout was performed. Windows BAT execution and physical printing are not certified by Linux CI.

## Updating

Close the previous launcher, extract the complete 1.2 ZIP, and start `START_PROXY_FOUNDRY.bat`. Decks and uploaded assets remain in the same local workspace outside the extracted app directory. Generate previously prepared decks once to apply v58. Old PNG assets and already-built order snapshots are preserved; build a new order to use the updated images.

An installed integrated **1.0.0 print helper is unchanged** and does not need replacement. Scryfall's year/week cache policy, custom templates, artist/modification credits and explicit back pairing remain in place.
