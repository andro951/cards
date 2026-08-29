# Card Conjurer proxy rules — repository-wide

This is the common handoff for every card project in `andro951/cards`. Read this file before a project-specific `STYLE_RULES.md`.

Project folders (for example `derevi/` or `doctor_who/`) should contain only project-specific data/assets/rules. If a rule or helper applies to every project, it belongs at repository root instead of being duplicated under one project.

## Source of truth and working order

- Repository: `andro951/cards`, branch `main`.
- GitHub is authoritative. Do not treat stale local `.cardconjurer` files as the source of truth.
- At the start of a task, fetch the live repository tree, this root rules file, the target project's own `STYLE_RULES.md` if it has one, and the current project `.cardconjurer` file.
- Project-specific rules override this file only where they explicitly say so.
- After changing card data, push the updated project file to GitHub and re-fetch/verify the resulting commit before reporting completion.
- Card-data work does **not** imply artwork generation/editing. Do not generate or alter artwork unless the user explicitly asks for image generation/editing.

## Current card data: use Scryfall Oracle data

For every real Magic card being added or audited:

1. Look up the exact current card by name in Scryfall.
2. Use current Scryfall fields as the mechanical source of truth:
   - `name`
   - `mana_cost`
   - `type_line`
   - `oracle_text`
   - `power`
   - `toughness`
   - `colors`
   - `layout`
3. Check `card_faces` for multi-face/special-layout cards instead of flattening or guessing.
4. Verify the returned Scryfall card page when practical.
5. Use current Oracle wording, not remembered wording or an old printing's text.

The custom part of these projects is the presentation/art. Do not silently rewrite card mechanics.

## Typography / character safety

Card Conjurer can render some Unicode punctuation poorly. After fetching Scryfall data, normalize visible card text where needed:

- em dash / en dash / minus (`—`, `–`, `−`) -> normal hyphen separator ` - `
- smart apostrophes/quotes -> straight ASCII `'` and `"`
- unusual non-breaking spaces -> ordinary spaces
- do not allow replacement/square characters in title, mana, type, rules, or P/T text

Example: `Creature - Human Cleric`, not `Creature — Human Cleric`.

## Learn Card Conjurer's frame system instead of guessing

Do not force an unfamiliar card into the closest frame already used by another project.

When a project needs a new card type/frame/layout:

1. Find the relevant Card Conjurer `group*.js` entry. This tells you which frame packs/layouts the UI exposes.
2. Open the corresponding `pack*.js` file. Record:
   - actual PNG asset paths
   - masks
   - layer names/order
   - bounds
   - complementary pieces
   - crown/P-T/special helper layers
3. Find the associated card version/layout definition and record:
   - saved `version`
   - `artBounds`
   - title/type/rules/mana/P-T geometry
   - set-symbol geometry
   - text colors
4. Reproduce the saved object from Card Conjurer's implementation rather than approximating by eye.
5. Add the newly learned reusable recipe to this root file if it is generally useful, or to the project rules if it is project-specific.

Useful search targets include `packM15...`, `packSaga...`, `packBattle...`, `packVehicle...`, `packAdventure...`, `pack...Legend...`, and distinctive frame names visible in the Card Conjurer UI.

For unusual layouts such as Sagas, Battles, Adventures, DFCs, Classes, Vehicles, etc., inspect the real Card Conjurer source before building the object.

**Principle:** Scryfall tells you what the card is. Card Conjurer's source tells you how that kind of card should be represented.

## Standard M15 baseline geometry

For ordinary modern M15-style cards, this is the repository baseline unless a project or special frame requires otherwise.

Card canvas:
- width `2010`
- height `2814`
- margins `0`

Standard art bounds:
- `x = 0.0767`
- `y = 0.1129`
- `width = 0.8476`
- `height = 0.4429`

Standard text geometry:
- Mana: `y=0.0613`, `width=0.9292`, `height=0.03380952380952381`, `size=0.043345543345543344`, right aligned, `shadowX=-0.001`, `shadowY=0.0029`, `manaCost=true`, `manaSpacing=0`.
- Title: `x=0.0854`, `y=0.0522`, `height=0.0543`, font `belerenb`, size `0.0381`.
- Type: `x=0.0854`, `y=0.5664`, `height=0.0543`, font `belerenb`, size `0.0324`.
- Rules: `x=0.086`, `y=0.6303`, `width=0.828`. Use the frame version's correct height; ordinary Derevi-style M15 cards currently use `0.26297085998578534`, while Generic Showcase/full-art versions may use `0.2875`.
- P/T: `x=0.7928`, `y=0.902`, `width=0.1367`, `height=0.0372`, size `0.0372`, font `belerenbsc`, centered.

### Standard type width

For the ordinary M15 template, type text width is `1540 / 2010 = 0.7661691542288557`.

### Standard dynamic title width

For ordinary M15 cards, title width is:

`1680 - (95 × number of mana symbols) px`

Count each printed `{...}` mana symbol, including `{0}`.

Examples:
- 0 symbols: `1680 px` = `0.835820895522388`
- 1 symbol: `1585 px` = `0.7885572139303483`
- 2 symbols: `1490 px` = `0.7412935323383084`
- 3 symbols: `1395 px` = `0.6940298507462687`

A special frame/layout may define different geometry. Follow its Card Conjurer version instead of forcing these standard values.

## Exact centered art auto-fit

Prefer storing deterministic `artX`, `artY`, `artZoom`, and `artRotate` rather than requiring the user to press Auto Fit later.

The repository-root `auto_fit_art.js` is a generic fallback that calls Card Conjurer's own `autoFitArt()`, but precomputing saved values is preferred.

For any frame, derive the fit from **that frame's actual art bounds**.

Let:
- `IW`, `IH` = source image dimensions
- `CW=2010`, `CH=2814`
- art bounds = `(x, y, width, height)`

First reproduce Card Conjurer's pixel-rounded box:
- `BX = round(x × CW)`
- `BY = round(y × CH)`
- `BW = round(width × CW)`
- `BH = round(height × CH)`

If `IW / IH > BW / BH`, fit by height:
1. `zoomPercent = round_to_1_decimal((BH / IH) × 100)` exactly like JavaScript `.toFixed(1)`.
2. `Z = zoomPercent / 100`.
3. `Ypx = BY`.
4. `Xpx = Math.round(BX - ((Z × IW) - BW) / 2)`.
5. `artX = Xpx / CW`.
6. `artY = Ypx / CH`.
7. `artZoom = Z`.
8. `artRotate = "0"`.

Otherwise fit by width:
1. `zoomPercent = round_to_1_decimal((BW / IW) × 100)`.
2. `Z = zoomPercent / 100`.
3. `Xpx = BX`.
4. `Ypx = Math.round(BY - ((Z × IH) - BH) / 2)`.
5. `artX = Xpx / CW`.
6. `artY = Ypx / CH`.
7. `artZoom = Z`.
8. `artRotate = "0"`.

JavaScript `Math.round` rounds `.5` toward positive infinity; do not substitute banker's rounding for exact edge cases.

For the standard art box, Card Conjurer rounds to:
- `BX=154`, `BY=318`, `BW=1704`, `BH=1246`

Example `1536×1024` standard art:
- fit by height
- `artZoom=1.217`
- `artX=71/2010=0.035323383084577116`
- `artY=318/2814=0.11300639658848614`

Preserve a user-approved hand crop unless asked to recalculate it.

## Standard frames

Default ordinary-frame sources:

- White: `/img/frames/m15/regular/m15FrameW.png`
- Blue: `/img/frames/m15/regular/m15FrameU.png`
- Black: `/img/frames/m15/regular/m15FrameB.png`
- Red: `/img/frames/m15/regular/m15FrameR.png`
- Green: `/img/frames/m15/regular/m15FrameG.png`
- Multicolor: `/img/frames/m15/regular/m15FrameM.png`
- Artifact: `/img/frames/m15/regular/m15FrameA.png`
- Land: `/img/frames/m15/regular/m15FrameL.png`

Creatures use the matching P/T treatment. Noncreatures have blank P/T text and normally no P/T frame.

### Enchantments / Nyx

By default, enchantments use M15 Nyx framing, including enchantment creatures. Use the matching Nyx color/artifact/multicolor source while preserving the correct M15 masks.

Legendary status and Nyx status are independent: a legendary enchantment uses both its Nyx treatment and the appropriate crown.

### Standard legendary crowns

Every permanent whose current type line contains `Legendary` gets exactly one appropriate legendary crown unless its special layout defines another crown treatment. Nonlegendary cards do not get crowns because of rarity.

Standard crowns:
- W: `/img/frames/m15/crowns/m15CrownW.png`
- U: `/img/frames/m15/crowns/m15CrownU.png`
- B: `/img/frames/m15/crowns/m15CrownB.png`
- R: `/img/frames/m15/crowns/m15CrownR.png`
- G: `/img/frames/m15/crowns/m15CrownG.png`
- M: `/img/frames/m15/crowns/m15CrownM.png`
- A: `/img/frames/m15/crowns/m15CrownA.png`
- L: `/img/frames/m15/crowns/m15CrownL.png`

Standard crown bounds:
`{height:0.1667, width:0.9454, x:0.0274, y:0.0191}`

## Repository-wide footer / metadata convention

Unless a project explicitly overrides it:

- Artist is exactly `ChatGPT`.
- Artist line uses Card Conjurer's artist glyph string: `{fontbelerenbsc}{fontsize3}{upinline1}￮{savex2}{elemidinfo-artist}`.
- Footer legal line is exactly `Custom Proxy • Personal Use Only`.
- Keep collector number, rarity code, set code, language metadata, serial fields, Wizards legal text, and bottom-right line blank.
- Do not add `CardConjurer.com`.
- Watermark stays disabled (`watermarkOpacity=0`, left/right `none`).

## Set symbols

Set-symbol artwork is project-specific, but the behavior is common:

- Use the symbol matching the card's intended/original printed rarity.
- A project that uses custom symbols should provide the complete rarity family it needs (normally mythic/rare/uncommon/common).
- Never silently substitute the wrong rarity symbol.
- Record the project's symbol folder and raw URL pattern in that project's `STYLE_RULES.md`.
- Set-symbol placement baseline:
  - `setSymbolX = 0.8522388059701492`
  - `setSymbolY = 0.5692963752665245`
  - `setSymbolZoom ≈ 0.101`
  - `setSymbolBounds = {x:0.9213, y:0.591, width:0.12, height:0.041, vertical:'center', horizontal:'right'}`

## Artwork file handling

- Store project artwork under that project's dedicated art folder.
- Prefer lowercase snake_case filenames for newly created assets unless the project already follows another naming scheme.
- Do not resize, stretch, or destructively crop source PNGs just to make them fit a card.
- Use `artX`, `artY`, `artZoom`, and the frame's `artBounds`.
- Preserve existing filenames when renaming would break saved card-data references.
- Record each project's raw art URL pattern in its project rules.

## Full-art land recipes

There are four distinct approved land presentations. Do not conflate them.

### 1. Full art land — framed

Use for a premium full-art land that still has a visible conventional outer land frame.

- `version = "m15ClearTextboxes"`.
- Use the M15 Full Art land family under `/img/frames/m15/new/fullart/`.
- Use the Full Art layout's tall art region, not the standard 3:2 art window.
- Keep the outer `Frame` and `Border` layers.
- Use land-specific Full Art assets rather than ordinary colored permanent frames.
- For two-color lands, split the relevant land-frame components with left/right masks.
- A one-line parenthetical mana reminder may be italic and centered.

### 2. Full art land — framed legendary

Start from the framed full-art recipe.

- Add the dedicated land legendary crown rather than a colored-permanent crown.
- The crown should communicate **legendary land first**.
- Keep the full-art land `Frame` and `Border` layers underneath.
- Color association should come mainly from the land accents/pinline/rules treatment.

### 3. Full art land — “no” frame / true borderless

Use for modern borderless/showcase land presentation.

- `version = "genericShowcase"`.
- Use native Generic Showcase assets under `/img/frames/m15/genericShowcase/`.
- Do not use the older `Borderless (Alt)` family unless specifically requested.
- `artBounds = {x:0, y:0, width:1, height:0.9224}`.
- Do not add the conventional outer `Frame` layer.
- Keep the neutral Generic Showcase land `Border` mask; it provides the clean solid-black footer/bottom treatment used by the approved borderless lands.
- Use masked Generic Showcase pieces for title, type, rules, and pinline.
- Title/type normally use a neutral/dark translucent land treatment.
- Two-color rules boxes use a darker translucent split-color treatment.
- Borderless title/type/rules text is normally white/light for legibility.
- Only sparse reminder-text rules should be centered; real Oracle text stays left-aligned.

### 4. Full art land — “no” frame legendary

Start from the true-borderless recipe.

- Add `/img/frames/m15/crowns/m15CrownLFloating.png`.
- Use `/img/frames/m15/crowns/m15CrownFloatingOutline.png`.
- The `Legend Crown Lower Cutout` helper may be used with `/img/black.png`, bounds `x=.0734, y=.1096, width=.8532, height=.0143`, `erase=true`.
- **Do not use `Legend Crown Border Cover` in this true-borderless legendary-land recipe.** It is a literal black strip and creates an obvious rectangular bar beneath the crown over edge-to-edge artwork.
- Floating crown bounds: `x=.0307, y=.0191, width=.9387, height=.1024`.
- Crown outline bounds: `x=.028, y=.0172, width=.944, height=.1062`.
- Keep the neutral Generic Showcase land `Border` mask so the bottom matches the nonlegendary borderless land cycle.
- Use the **neutral land-colored** crown, not a green/blue/etc. crown merely because the land is associated with that color.
- Color identity belongs mainly in the pinline/rules panel.

## Generic Scryfall helper

Repository root contains `fetch_scryfall_deck.py`.

Use it for project deck/checklist refreshes rather than copying a deck-specific fetch script into every project:

`python fetch_scryfall_deck.py --deck-id <scryfall-deck-id> --output-dir <project-folder>`

It writes:
- `scryfall_proxy_export.json`
- `scryfall_proxy_cards.json`
- `scryfall_proxy_decklist.txt`

Project-specific workflows can call the common helper with their own deck ID/output folder.

## Safe update workflow

1. Fetch the live repository tree.
2. Read this root rules file.
3. Read the target project's own rules and current `.cardconjurer`.
4. Refresh/verify Scryfall data when mechanics are involved.
5. Determine the correct frame from Scryfall type/layout **and Card Conjurer source**.
6. Apply the correct geometry/layers/masks rather than guessing.
7. Determine source image dimensions and calculate saved Auto Fit values unless preserving an approved crop.
8. Preserve the repository-wide footer convention and the project's set-symbol convention.
9. Validate card keys, frames, legendary status, layout-specific requirements, asset paths, and visible text.
10. Push project changes to `main`.
11. Re-fetch the final repository state and verify the commit.

If a large one-line `.cardconjurer` file is inconvenient to update directly through a connector, a temporary small Python updater + path-triggered GitHub Action is acceptable. Remove the temporary workflow/script after it succeeds.

## What belongs where

Repository root:
- common rules (`STYLE_RULES.md`)
- reusable helpers (`auto_fit_art.js`, `fetch_scryfall_deck.py`)
- genuinely cross-project tooling

Project folder:
- `.cardconjurer` data
- art
- set-symbol assets
- project deck/checklist data
- audit snapshots
- project-specific rules and exceptions
- project-specific workflows/configuration references

If a new rule is useful to all projects, update this root file instead of copying it into one project's handoff.

## Borderless land text/readability conventions

For projects using light text over translucent full-art land panels:

- Land rules text should be vertically centered unless a project explicitly documents a different layout.
- Parenthetical mana/tap reminder text should be horizontally centered. If it is the only rules text, center it horizontally and vertically.
- When a centered reminder precedes normal Oracle text, use Card Conjurer inline alignment (`{center}` for the reminder, then `{left}` for the Oracle text) rather than centering the Oracle text.
- Projects may increase the Rules Text horizontal inset when the native Generic Showcase geometry visually crowds the border; record the exact project geometry in the project rules.
- For **white** Generic Showcase/land Rules fills used with white rules text, preserve the white asset hue but use **`opacity: 85` on the white Rules layer only**. Do not reduce opacity on the white pinline. This is the standard white-land readability override unless a project explicitly chooses another value.
- Five-color/rainbow utility lands should use Card Conjurer's native multicolored/gold land treatment for pinline and rules-panel color rather than a neutral gray land treatment.

### Compact borderless land boxes for very sparse text

For a true-borderless project, do **not** switch the whole card to M15 Extended Art (Shorter Textbox) merely to get a smaller lower box. The full `m15ExtendedArtShort` frame adds its own extended-art outer frame and changes the art window, which is visually different from Generic Showcase borderless.

When a land has only a tiny amount of text (for example a basic-land mana hint or an original dual with only the reminder line), use this approved **compact borderless hybrid** instead:

- keep `version = "genericShowcase"`
- keep Generic Showcase full-art bounds: `artBounds = {x:0, y:0, width:1, height:0.9224}`
- keep the neutral Generic Showcase title treatment and Generic Showcase neutral bottom/footer `Border` mask
- use the M15 Extended Art (Shorter Textbox) **lower-box assets only**:
  - pinline mask `/img/frames/m15/boxTopper/short/pinline.svg`
  - type mask `/img/frames/m15/boxTopper/short/type.png`
  - rules mask `/img/frames/m15/boxTopper/short/text.svg`
  - neutral lower-box source `/img/frames/m15/boxTopper/short/l.png`
  - colored land sources `wl.png`, `ul.png`, `bl.png`, `rl.png`, `gl.png`, `ml.png` from the same folder
- **do not add** `/img/frames/m15/boxTopper/short/frame.svg`
- **do not use** the short package's conventional outer `Border`; retain the Generic Showcase land footer/border instead
- set-symbol bounds use `y=0.6343`
- type `y=0.61`
- rules `y=0.6743`, `height=0.2448`
- preserve the project's normal side padding; for the current Doctor Who/Derevi projects this is `x=0.105`, `width=0.79`
- sparse reminder-only text is centered horizontally and vertically

Only use this compact hybrid when the text is genuinely sparse. Lands with normal Oracle paragraphs, multiple abilities, cycling, shock-land text, fetch text, or meaningful flavor blocks stay on the normal Generic Showcase lower box. Split-color compact lands still use the usual Right Half mask, and any white Rules layer uses the repository white-land opacity override.
