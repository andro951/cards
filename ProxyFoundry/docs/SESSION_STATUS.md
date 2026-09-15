# Proxy Foundry 1.1 — verified artist-credit and Card Tools v54 update

## Verified source and test result

Application/test source: commit `7345ebb47250ac7334a4ffa08481f1098a25d679` in `andro951/cards`.

Proxy Foundry CI run: `35030300036`, job `104587213716`, completed successfully on 15 September 2026. The machine-readable JUnit report contains **134 cases: 132 passed, 0 failed, 0 errors, 2 intentionally skipped**, in 156.256 seconds. The two skipped cases are the optional offline-only DOM suite; real HTTP/browser tests were enabled and passed. The verification document was added after that run; executable source is unchanged.

The test command enabled `PF_BROWSER=1` and `PF_LIVE_CC=1`. It includes:

- Real HTTP Chromium flows for imports, setup, quantities, template creation, mobile layout, order review, per-card artists and modification credits.
- The genuine pinned CardConjurer renderer, including 11 output faces for 10 physical cards: creature, triome, legendary land, artifact creature, Esika/Bridge, Saga, planeswalker, Budoka/Dokai Flip, multicolored Vehicle and Iron Man.
- Per-face Scryfall artist preservation, custom artist inheritance/overrides, modification suffix inheritance/overrides/suppression, native artist-strip export, backup/duplicate persistence and render invalidation.
- The actual installed MV3 helper transferring an exact multi-chunk paired ZIP to a new tab. The merchant editor is a controlled fixture; no live checkout or payment occurs.
- Compiler parity, exact vendor hashes, cache rules, source separation, set-symbol/type geometry, custom-template preservation and release ZIP integrity.

## Reproduced and corrected during this update

The new browser test exposed a real modal autofocus race: a 20 ms callback could move typing from Modification credit into Quantity. The dialog now focuses synchronously when mounted. A deterministic component test fails against the old callback and passes with the fix, checking that the quantity stays unchanged.

A follow-up test run exposed a test synchronization error: it began a direct backend regeneration before the UI save finished. The app correctly rejected that concurrent write. The test now waits for the saved dialog to close; revision-conflict protection was not weakened.

## Supplied v54 preservation and comparison

All ten distributed Card Tools source/document files match the supplied `MTG_Card_Pipeline_Local_UI_v54(1).zip` byte-for-byte. Its SHA-256 is `67136267239e3a4d025a0b8156a428a7a472e7473965bb55ebd67e99ebc12def`. Per-file hashes are recorded in `CARD_TOOLS_V54_MANIFEST.json` and checked by tests.

Compared with the v48 vendor actually used by the earlier app, four files changed and six are identical. The embedded `LAYOUTS` library has 20 entries in both versions and is exactly equal. The changed behavior is in procedural recipe logic and ingestion: real-art credits, native single-card Flip layouts, normal Iron Man routing, multicolored Vehicle title/type bars, and dimension-aware set-symbol placement. See `CARD_TOOLS_V54_REVIEW.md` for the detailed analysis.

The new artist/modification controls are implemented in Proxy Foundry's adapter and UI. The supplied vendor code itself is unmodified. Custom template geometry remains authored by the user rather than silently receiving the built-in geometry pass.

## Installation and existing data

The release is one ZIP containing one `ProxyFoundry` folder. Extract once and double-click `START_PROXY_FOUNDRY.bat`; do not open `site/index.html` directly. The clean extracted Python launcher was also smoke-tested with a separate temporary workspace, and all main UI modules were served successfully. No existing user decks were touched by that test.

Existing prepared decks need regeneration once for the v54/credit update. Old PNG assets and saved order ZIPs are retained, not rewritten. Quantity/back-only changes still reuse front renders after regeneration.

The four printer-helper files are byte-identical to the previous integrated helper version 1.0.0. An installed 1.0.0 helper needs no replacement for this update. Older 0.9.x test helpers are different and use the setup instructions in README.md.

The distribution excludes font files, runtime caches, browser profiles, private keys and artwork repository archives. It includes a SHA-256 release manifest. Only individual required upstream CardConjurer files are fetched at runtime.

## Verification boundaries

The supplied Windows BAT files are not executed by Linux CI. The clean Python launch test is not a Windows installation test. Live merchant UI changes and physical print alignment remain outside automated proof; review the actual printer proof before purchasing. The optional user land-library URL remains configurable and unset until supplied.
