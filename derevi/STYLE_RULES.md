# Derevi proxy project handoff / style rules

This file is the complete handoff for a fresh thread. Read it before modifying any Derevi proxy data.

## Source of truth and first steps

- Repository: `andro951/cards`, branch `main`.
- Project folder: `derevi/`.
- Card Conjurer source of truth: `derevi/derevi_cards.cardconjurer`.
- GitHub is authoritative. Do not use old local `.cardconjurer` copies as the source of truth.
- At the start of a new update, fetch the live recursive GitHub tree, then fetch the current `derevi_cards.cardconjurer` and this file before editing.
- Scryfall deck/checklist: `https://scryfall.com/@andro951/decks/cac4a3fa-84f8-4b8e-b946-0d8a8086fd9d` and `derevi/scryfall_proxy_decklist.txt`.
- Do not hard-code the card count. Compare the live Scryfall list, live PNG files, and current Card Conjurer entries each time. Include any explicit user-requested extras.
- `PROXY_SYNC_STATUS.md`, `SCRYFALL_RULES_AUDIT.md`, and `scryfall_current_cards.json` are useful audit snapshots, but they can become stale and must not replace a fresh Scryfall lookup.

## Current card data: always use Scryfall Oracle data

For every card being added or audited:

1. Look up the exact current card by name in Scryfall, preferably `https://api.scryfall.com/cards/named?exact=<name>`.
2. Use the current Scryfall fields for:
   - `name`
   - `mana_cost`
   - `type_line`
   - `oracle_text`
   - `power`
   - `toughness`
   - `colors`
3. Fetch/check the returned `scryfall_uri` card page as a verification step.
4. Use current Oracle wording, not original-printing text, old release-note wording, or remembered wording.
5. If Scryfall changes wording later, update the proxy to the new current Oracle text.
6. For multi-face/special-layout cards, inspect `card_faces` and handle the layout explicitly instead of guessing.

The visible proxy wording should match current Scryfall semantically, with only the punctuation-safety substitutions below.

## Typography / character safety

Card Conjurer has shown rendering problems with some Unicode punctuation, so visible card text uses safe ASCII punctuation after Scryfall data is fetched.

- Convert em dash / en dash / minus (`—`, `–`, `−`) to a normal hyphen: ` - ` where used as a separator.
- Convert smart apostrophes/quotes to straight ASCII `'` and `"`.
- Convert unusual non-breaking spaces to ordinary spaces.
- Do not allow replacement/square characters in title, mana, type, rules, or P/T text.
- Example type line: `Creature - Human Cleric`, not `Creature — Human Cleric`.

## Canonical Card Conjurer geometry

Use Derevi's current card object as the canonical geometry/template. Other cards should differ only where the card itself requires it: card text, title width, rules font size, frames, P/T presence, and art placement.

Card canvas:
- Width: `2010`
- Height: `2814`
- Margins: `0`

Art bounds:
- `x = 0.0767`
- `y = 0.1129`
- `width = 0.8476`
- `height = 0.4429`

Text geometry copied from Derevi:
- Mana: `y=0.0613`, `width=0.9292`, `height=0.03380952380952381`, `size=0.043345543345543344`, right aligned, `shadowX=-0.001`, `shadowY=0.0029`, `manaCost=true`, `manaSpacing=0`.
- Title: `x=0.0854`, `y=0.0522`, `height=0.0543`, font `belerenb`, size `0.0381`; width is dynamic by the formula below.
- Type: `x=0.0854`, `y=0.5664`, `height=0.0543`, font `belerenb`, size `0.0324`; width is fixed by the rule below.
- Rules: `x=0.086`, `y=0.6303`, `width=0.828`, `height=0.26297085998578534`; start from Derevi's current rules size and shrink only as needed for longer text. Do not change the rules box geometry merely to fit text.
- P/T: `x=0.7928`, `y=0.902`, `width=0.1367`, `height=0.0372`, size `0.0372`, font `belerenbsc`, centered.

### Type width

Type text box width is always exactly **1560 px**:

`1560 / 2010 = 0.7761194029850746`

### Title width

Title text box width is:

`1680 - (95 × number of mana symbols) px`

Count each `{...}` mana symbol in the printed mana cost, including `{0}`. Lands with no mana cost have 0 symbols.

Examples:
- 0 symbols: `1680 px` = `0.835820895522388`
- 1 symbol: `1585 px` = `0.7885572139303483`
- 2 symbols: `1490 px` = `0.7412935323383084`
- 3 symbols: `1395 px` = `0.6940298507462687`

## Exact centered art auto-fit calculation

Preferred future behavior: calculate and store `artX`, `artY`, and `artZoom` directly from the source image dimensions. The user should not need to press Card Conjurer's Auto Fit button or manually run a script.

This reproduces Card Conjurer's official `autoFitArt()` behavior for the standard art box.

Let:
- `IW` = source image width in pixels
- `IH` = source image height in pixels
- Card width `CW = 2010`
- Card height `CH = 2814`

Card Conjurer rounds the art-box dimensions to pixels first:
- `BX = round(0.0767 × 2010) = 154`
- `BY = round(0.1129 × 2814) = 318`
- `BW = round(0.8476 × 2010) = 1704`
- `BH = round(0.4429 × 2814) = 1246`
- Art-box aspect ratio = `1704 / 1246 ≈ 1.367576244`

Card Conjurer resets rotation to zero.

### If the source image is wider than the art box

Condition:

`IW / IH > BW / BH`

Fit by height:

1. `zoomPercent = round_to_1_decimal((BH / IH) × 100)` exactly like JavaScript `.toFixed(1)`.
2. `Z = zoomPercent / 100` (`artZoom`).
3. `Ypx = BY = 318`.
4. `Xpx = Math.round(BX - ((Z × IW) - BW) / 2)`.
5. `artX = Xpx / 2010`.
6. `artY = Ypx / 2814`.
7. `artZoom = Z`.
8. `artRotate = "0"`.

### If the source image is equal/narrower than the art box

Condition:

`IW / IH <= BW / BH`

Fit by width:

1. `zoomPercent = round_to_1_decimal((BW / IW) × 100)` exactly like JavaScript `.toFixed(1)`.
2. `Z = zoomPercent / 100`.
3. `Xpx = BX = 154`.
4. `Ypx = Math.round(BY - ((Z × IH) - BH) / 2)`.
5. `artX = Xpx / 2010`.
6. `artY = Ypx / 2814`.
7. `artZoom = Z`.
8. `artRotate = "0"`.

To mimic JavaScript `Math.round` in another language, remember that it rounds to the nearest integer with `.5` toward positive infinity; do not blindly use a language's banker's-rounding function for exact edge cases.

Example for a `1536 × 1024` image:
- Aspect = `1.5`, so fit by height.
- `zoomPercent = 121.7`, so `artZoom = 1.217`.
- `Xpx = 71`, `Ypx = 318`.
- `artX = 71 / 2010 = 0.035323383084577116`.
- `artY = 318 / 2814 = 0.11300639658848614`.

If PNG dimensions are not exposed by the GitHub connector, read the PNG IHDR directly from repository bytes: width/height are big-endian unsigned 32-bit integers at bytes `16:24` (`struct.unpack('>II', data[16:24])`). A temporary GitHub Action can do this when necessary. Do not infer dimensions from file size or old local copies.

`derevi/auto_fit_art.js` remains available as a fallback and calls Card Conjurer's own `autoFitArt()` on load, but precomputing/storing the values is preferred for deterministic saved-card data.

Preserve user-approved or hand-adjusted art placement. Recalculate only when adding new art, when the user explicitly asks for official auto-fit, or when the existing values are known to be placeholders/bad.

## Frames

Default to M15-style frames and preserve the existing Card Conjurer mask/layer structure.

Base frame follows card type/color:
- White: `/img/frames/m15/regular/m15FrameW.png`
- Blue: `/img/frames/m15/regular/m15FrameU.png`
- Black: `/img/frames/m15/regular/m15FrameB.png`
- Red: `/img/frames/m15/regular/m15FrameR.png`
- Green: `/img/frames/m15/regular/m15FrameG.png`
- Multicolor: `/img/frames/m15/regular/m15FrameM.png`
- Artifact: `/img/frames/m15/regular/m15FrameA.png`
- Land: `/img/frames/m15/regular/m15FrameL.png`

For creatures, include the matching P/T frame. Noncreatures have blank P/T text and normally no P/T frame.

### Enchantments / Nyx

- Every enchantment uses the M15 Nyx frame by default, including enchantment creatures.
- Nyx sources follow the same color code, e.g. blue `/img/frames/m15/nyx/m15FrameUNyx.png`, green `/img/frames/m15/nyx/m15FrameGNyx.png`, multicolor `M`, artifact `A`, etc.
- Keep the same Derevi-derived geometry and masks unless the card itself genuinely requires a small adjustment.

### Legendary crowns

- Every permanent whose current Scryfall type line contains `Legendary` gets exactly one appropriate M15 legendary crown.
- Nonlegendary cards never get a legendary crown, regardless of rarity.
- Crown follows the active frame type/color:
  - W: `/img/frames/m15/crowns/m15CrownW.png`
  - U: `/img/frames/m15/crowns/m15CrownU.png`
  - B: `/img/frames/m15/crowns/m15CrownB.png`
  - R: `/img/frames/m15/crowns/m15CrownR.png`
  - G: `/img/frames/m15/crowns/m15CrownG.png`
  - M: `/img/frames/m15/crowns/m15CrownM.png`
  - A: `/img/frames/m15/crowns/m15CrownA.png`
  - L: `/img/frames/m15/crowns/m15CrownL.png`
- Crown bounds: `height=0.1667`, `width=0.9454`, `x=0.0274`, `y=0.0191`.
- Nyx and legendary status are independent: a legendary enchantment uses both Nyx and the appropriate crown.

## Shared project assets and footer

Shared assets:
- Set symbol: `https://raw.githubusercontent.com/andro951/cards/main/derevi/derevi_set_symbol.png`
- Bottom wings emblem: `https://raw.githubusercontent.com/andro951/cards/main/derevi/wings_emblem.png`

Set symbol placement:
- `setSymbolX = 0.8522388059701492`
- `setSymbolY = 0.5692963752665245`
- `setSymbolZoom ≈ 0.101`
- `setSymbolBounds = {x:0.9213, y:0.591, width:0.12, height:0.041, vertical:'center', horizontal:'right'}`

Bottom wings emblem bounds:
- `width = 0.19701492537313434`
- `height = 0.08443496801705758`
- `x = 0.4223880597014925`
- `y = 0.8906183368869937`

Footer / metadata:
- Artist is exactly `ChatGPT`.
- Artist line uses Card Conjurer's paintbrush/artist glyph string: `{fontbelerenbsc}{fontsize3}{upinline1}￮{savex2}{elemidinfo-artist}`.
- Footer legal line is exactly: `Custom Proxy • Personal Use Only`.
- No collector number, rarity code, set code, language metadata, serial fields, Wizards legal text, or `CardConjurer.com` footer.
- Keep `infoNumber`, `infoRarity`, `infoSet`, `infoLanguage`, `infoNote`, serial fields, Wizards line, and bottom-right line blank.
- Watermark stays disabled (`watermarkOpacity = 0`, left/right `none`).

## Artwork file handling

- Do not resize, stretch, crop, or otherwise modify source PNG files merely to fit the card.
- Use `artX`, `artY`, and `artZoom` for framing/cropping.
- Raw art URL format: `https://raw.githubusercontent.com/andro951/cards/main/derevi/<filename>.png`.
- Preserve existing filenames even if an old filename has a typo; do not rename assets casually because the card data may already reference them.
- For new assets, prefer lowercase snake_case filenames.

## Safe update workflow for a new thread

1. Fetch the live repo tree (`main?recursive=1`).
2. Fetch this file and the current `derevi_cards.cardconjurer`.
3. Refresh the live Scryfall deck/checklist and identify cards/art not yet represented.
4. For every affected card, fetch current Scryfall exact-name data and verify its current Scryfall page.
5. Apply current mana/type/Oracle/P-T data, then perform the ASCII punctuation normalization.
6. Copy Derevi's canonical geometry; apply the dynamic title-width rule and fixed type width.
7. Choose the correct base frame; use Nyx for enchantments; add a crown iff the current type line is legendary.
8. Determine actual PNG dimensions and calculate official centered auto-fit values with the equations above unless the user has already approved/manual-fit that art.
9. Preserve artist/footer/set-symbol/wings/no-metadata conventions.
10. Verify every expected PNG exists, every card key is unique, current Scryfall checklist entries are present, legendary/nonlegendary crown status is correct, enchantments use Nyx, and visible text contains no unsafe Unicode punctuation.
11. Push the updated `derevi_cards.cardconjurer` directly. If the connector cannot conveniently update the large one-line JSON, use a temporary small Python script + path-triggered GitHub Action, let it modify/commit the file, then remove the temporary script/workflow/trigger.
12. Re-fetch the final repo state and verify the resulting blob/commit before reporting completion.

If the user supplies a newly exported `.cardconjurer` file containing official Card Conjurer Auto Fit or hand-tuned art changes, preserve those user-approved art placement values when merging into the GitHub master unless the user explicitly asks to recalculate them.

## Land presentation
- Savannah, Tropical Island, and Tundra use a multicolored M15 treatment rather than the plain generic land frame.
- Their current Scryfall parenthetical mana abilities are shown in the rules box.
- Gaea's Cradle uses a green-inflected frame and green legendary crown.
- Sparse land rules text may be vertically repositioned/enlarged for intentional visual balance.

## Repository write rule
- If `derevi/derevi_cards.cardconjurer` is modified, commit/push the change to GitHub in the same task. A local-only edited copy is not considered completion unless the user explicitly asks for local-only work.
