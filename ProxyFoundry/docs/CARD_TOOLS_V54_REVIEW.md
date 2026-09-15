# Card Tools v48 → v54: comparison and Proxy Foundry integration

## Exact comparison basis

The old version is the actual `ProxyFoundry/vendor/card_tools` directory at verified application commit `355f3f4153049a4538523f6c72ff621e2ea9b6a7`. The new version is the supplied `MTG_Card_Pipeline_Local_UI_v54(1).zip`, not another repository copy with a similar name. Generated `__pycache__` files were excluded from the source comparison.

The supplied ZIP's SHA-256 is `67136267239e3a4d025a0b8156a428a7a472e7473965bb55ebd67e99ebc12def`. Exact hashes for every distributed source/document file are in `CARD_TOOLS_V54_MANIFEST.json`. The promoted vendor files match the upload byte-for-byte.

**Four files changed; six are byte-identical.**

| File | v48 bytes | v54 bytes | Result |
| --- | ---: | ---: | --- |
| `pipeline/card_data_to_cardconjurer.py` | 4,918,249 | 4,938,175 | Compiler behavior changed |
| `pipeline/scryfall_to_card_data.py` | 58,353 | 63,382 | Artist and nested Flip semantics changed |
| `pipeline/CARD_DATA_INPUT_INSTRUCTIONS.md` | 19,438 | 19,823 | Physical-card relationship documentation |
| `README_LOCAL_UI.txt` | 5,021 | 5,434 | Symbol alignment and Vehicle documentation |

The local UI, its BAT launcher, Scryfall deck importer, original-printing image downloader, copy-token utility and token example are all unchanged. No UI migration was needed inside the preserved Card Tools program.

Importing both compiler modules and recursively comparing their **`LAYOUTS` dictionaries returned exact equality**. The embedded template collection has not been replaced. The meaningful changes below are procedural recipe selection, construction and postprocessing.

## What changed in the supplied source

### 1. Correct artist attribution for original and fallback artwork

`pipeline/scryfall_to_card_data.py::scryfall_artist` prefers a nonblank face-specific artist and then the physical card's artist. `build_face_record` writes an explicit semantic `artist` only when the selected artwork actually comes from Scryfall, including fallback artwork. If Scryfall has no artist, it writes an empty value rather than attributing the image to the custom project's default artist.

`card_data_to_cardconjurer.py::build_one` now uses the semantic card's `artist` before `project.artist`. Explicitly empty per-card credits remain empty. Custom project artwork can still inherit the configured project artist.

**Integration:** Copying the new compiler alone would not fix Proxy Foundry, because its managed-deck workflow builds semantic records through its own adapter instead of invoking the original CLI. The adapter now passes actual artwork provenance to a dedicated credit resolver and sets the semantic artist accordingly.

### 2. Kamigawa Flip cards are one physical card

The updated ingestion nests the rotated lower face under `flip_face`. The compiler adds a native `flip` recipe with one shared center art window, separate upright/lower text, 180-degree lower rotation and P/T pieces required independently for each half. Its authoritative P/T pass handles both halves rather than treating the second face as a card back.

**Integration:** Proxy Foundry already grouped the physical entry as one face but previously rejected the layout. It now builds the v54 nested semantics, preserves both halves' flavor data, delegates to the native Flip recipe and packages the result with the deck's normal back. Budoka Gardener / Dokai is covered by regression and genuine-render tests. This does not make every unsupported multi-face structure automatically supported.

### 3. Iron Man's named full-art land exception is removed

The old `IRON_MAN_NAME` route and its full-art dual-land recipe branch are removed from the supplied compiler. Iron Man now follows the same semantic legendary artifact-creature treatment as other cards of those types.

**Integration:** The obsolete name-specific condition was removed from the optional Classic-template adapter as well. Automatic output delegates to v54's normal inference; no replacement Iron Man frame was invented.

### 4. Multicolored Vehicles get gold title/type bars

The new `set_title_type_frame_color` changes masked Title and Type bars to the multicolor M15 texture for Vehicles with two or more colors. The Vehicle body and P/T treatment remain Vehicle-specific. Both legendary and nonlegendary paths receive this change.

**Integration:** Inherited directly from the exact supplied compiler. Tests verify the gold bars and preserved Vehicle body rather than asserting that the whole card becomes a generic gold frame.

### 5. Set-symbol placement becomes dimension-aware

The supplied compiler adds `SET_SYMBOL_RIGHT_EDGE = 0.9213` and `SET_SYMBOL_TYPE_GAP = 0.0100`. It measures the symbol image's actual intrinsic dimensions and rendered zoom, anchors its right edge, centers it on the primary type text box, and adjusts overlapping type-line width to leave the gap.

Flip cards deliberately reserve space for the upright P/T medallion; their symbol right edge is placed before that P/T anchor, and the rotated lower type box reserves its own P/T space. This is an explicit exception to the ordinary right-edge anchor, not an integration defect.

**Integration:** Automatic/built-in recipes use v54's pass after selecting the actual uploaded/generated symbol. User-created custom templates retain their authored symbol and text geometry rather than silently receiving this built-in postprocessing. Tests cover both paths.

### 6. Clarifications, not new recipe changes

The new source comments explain existing land-family routing, colored-artifact body/accent treatment, Station layering and authoritative P/T ownership. In this diff, those comments do not constitute a redesign of the corresponding approved frames. Their existing behavior is retained.

## Artist and modification controls added to Proxy Foundry

The new modification-credit feature is separate from the v54 vendor code. The vendor remains unmodified.

- **Actual Scryfall artwork:** always uses the real artist from the selected printing/face. Deck-wide custom artists and per-card blank/override values cannot replace it.
- **Custom artwork:** uses its per-card artist when specified, otherwise the deck custom-art artist, otherwise the printing artist. A separate **Use the original printing artist for this custom image** option explicitly retains original attribution on modified or extended uploads.
- **Modification credit:** optional deck default and per-face override, such as `Modified by ChatGPT`. It is appended in the native artist spot as `Artist Name · Modified by ChatGPT`. A per-face suppression checkbox removes the deck suffix from just that face.

Both the deck setup and card inspector preview the composed artist line. The original Scryfall artist remains stored separately. Repeated generation does not append the suffix repeatedly, and credits cannot inject CardConjurer formatting commands.

Modification settings survive reusable style defaults, deck duplication, printing changes and backup/restore. Double-faced cards retain independent artists for their two sides.

## Existing projects, cache and unchanged components

A new generation-version key prevents an old cached PNG from being presented as an updated v54 render. Existing prepared decks are marked for regeneration once. Old PNG assets are retained; previously built order ZIP snapshots do not change. After regeneration, changing only a quantity or deck back still reuses the front render.

Scryfall's existing 365-day / 7-day cache policy remains unchanged. The pinned CardConjurer renderer and per-file download architecture remain unchanged. The printer helper files are byte-identical to the previous integrated version 1.0.0; no helper reinstall is needed for this update when that version is already connected.

## Verification and its scope

New tests cover source hashes, per-face artist precedence, missing-original credits, custom/Scryfall fallback transitions, per-card suffix overrides and suppression, compiler/export parity, duplication and backup persistence, render invalidation, native symbol geometry, custom-template preservation, Vehicle accents, Iron Man routing and single-card Flip pairing.

The browser suite exercises the actual card/deck artist controls over the local HTTP app. The native structural suite now requests **11 output faces for 10 physical cards**, including Esika/Bridge, Budoka/Dokai, a multicolored Vehicle and Iron Man. It uses the genuine pinned CardConjurer code/assets with clearly synthetic test artwork and card text, and saves native artist-strip images for inspection. Synthetic fixtures are not claims about official Oracle text.

The installed-extension regression still uses a controlled merchant editor: no live order or payment is performed. Windows BAT execution and physical print accuracy are not certified by Linux Chromium tests. Exact final test results belong to the corresponding CI run and release-verification record, not inferred from the presence of test code.
