# Doctor Who project rules

Read `../STYLE_RULES.md` first. That root file contains the repository-wide Card Conjurer rules, frame-discovery method, standard geometry, Auto Fit method, footer convention, and shared validation guidance. This file contains **Doctor Who-specific** details only.

## Project source of truth

- Project folder: `doctor_who/`
- Card Conjurer file: `doctor_who/doctor_who_cards.cardconjurer`
- Art folder: `doctor_who/art/`
- Set-symbol folder: `doctor_who/set_icon/`
- Current project size: **50 card-list slots / 51 Card Conjurer faces** because `Esika, God of the Tree // The Prismatic Bridge` is represented as two faces.
- `CARD_CONJURER_AUDIT.md` records the latest structural/frame audit. It is a verification snapshot; fresh card data and the live `.cardconjurer` file remain authoritative.

At the start of a Doctor Who update, fetch the live repository tree, `../STYLE_RULES.md`, this file, and `doctor_who_cards.cardconjurer`.

## Doctor Who asset paths

Raw art URL pattern:

`https://raw.githubusercontent.com/andro951/cards/main/doctor_who/art/<filename>.png`

Set symbols:
- Mythic: `https://raw.githubusercontent.com/andro951/cards/main/doctor_who/set_icon/mythic.png`
- Rare: `https://raw.githubusercontent.com/andro951/cards/main/doctor_who/set_icon/rare.png`
- Uncommon: `https://raw.githubusercontent.com/andro951/cards/main/doctor_who/set_icon/uncommon.png`
- Common: `https://raw.githubusercontent.com/andro951/cards/main/doctor_who/set_icon/common.png`

Preserve the current numbered art filenames unless the card data is updated in the same change. In particular, the modal pair uses:
- `12A_Esika_God_of_the_Tree.png`
- `12B_The_Prismatic_Bridge.png`

The Card Conjurer canvas is the repository standard `2010 × 2814`.

## Mechanical data

All real Magic card mechanics must use current Scryfall Oracle data. Do not paraphrase rules text or infer an old printing's wording.

For multi-face cards, use Scryfall `card_faces` and store each rendered face separately when Card Conjurer requires it. The current file therefore contains separate entries for `Esika, God of the Tree` and `The Prismatic Bridge`.

The current face order is intentional and must remain stable unless the user changes the project list. A normal validation pass should find exactly **51 unique keys**.

## Default nonland presentation

Ordinary nonlands inherit the root M15 geometry and footer convention.

- Use the color-appropriate M15 frame.
- Artifacts use the artifact frame.
- Enchantments use Nyx treatment.
- Legendary permanents use the appropriate legendary crown.
- Colored artifacts may use a colored pinline with the artifact body treatment when appropriate to the card.
- Vehicles use the actual Vehicle frame/P-T treatment rather than a generic artifact approximation.

Current examples:
- `Propaganda` and `Elven Chorus` use Nyx enchantment framing.
- `K-9, Mark I` uses an artifact creature treatment with blue identity/pinline and an artifact legendary crown.
- `RMS Titanic` uses the Vehicle frame/P-T treatment plus its legendary crown.
- `Wedding Ring` is **not legendary**; do not add a crown merely because it is mythic.

## The Fourteenth Doctor — native WHO treatment

`The Fourteenth Doctor` intentionally uses Card Conjurer's real **TARDIS (WHO)** showcase package rather than a generic M15 approximation.

- Saved version: `tardis`
- Use `/img/frames/tardis/` assets.
- Use the TARDIS package's own multicolor frame, P/T treatment, legendary crown, art bounds, text geometry, white text, and set-symbol placement.
- Do not replace this with a normal M15 multicolor frame unless explicitly requested.

## Esika // The Prismatic Bridge — modal DFC treatment

This card must remain a true two-face Modal DFC representation.

### Esika, God of the Tree
- Saved version: `modalRegular`
- Use the green Modal DFC **front** frame.
- Use the Modal DFC legendary crown treatment.
- Use the front-face icon/reminder geometry defined by Card Conjurer.

### The Prismatic Bridge
- Saved version: `modalRegular`
- Use the multicolor Modal DFC **back** frame.
- Layer the multicolor Nyx/enchantment treatment appropriate to a legendary enchantment.
- Use the Modal DFC legendary crown treatment.

Do not flatten the two faces into one ordinary M15 card.

## Doctor Who lands — full-art borderless baseline

The Doctor Who land suite intentionally uses Card Conjurer's **Generic Showcase / borderless** geometry for full-art presentation.

Common rules:
- saved version: `genericShowcase`
- full-width art treatment
- neutral land title/type treatment
- land border/footer treatment
- color identity appears through pinline/rules layers rather than turning the entire card into a normal spell-colored frame
- title/type/rules text is white for this treatment

This applies to fetchlands, shocklands, original duals, utility lands, basics, and the three-color land cycle unless a specific special rule below overrides it.

### Two-color lands

Two-color lands use true split color treatment:
- first color as the base pinline/rules layer
- second color applied with Card Conjurer's **Right Half** mask
- neutral land title/type treatment remains on top
- retain the neutral land border/footer layer

Examples include `Savannah`, `Tropical Island`, `Tundra`, `Steam Vents`, `Godless Shrine`, `Watery Grave`, and `Sacred Foundry`.

### Three-color lands / triome-style frames

Three-color lands must show all three colors. Do **not** approximate them as two-color frames.

Use three layers for both pinline and rules treatment:
1. first color as the base layer
2. second color with `/img/frames/maskMiddleThird.png`
3. third color with `/img/frames/maskRightHalf.png`

Current three-color lands:
- `Raffine's Tower` — U/B/W
- `Spara's Headquarters` — W/U/G
- `Jetmir's Garden` — G/W/R
- `Zagoth Triome` — G/U/B
- `Indatha Triome` — B/G/W
- `Ketria Triome` — U/R/G
- `Raugrin Triome` — R/W/U

The exact layer order above matches the current saved file and should be preserved unless a visual redesign is intentional.

### Legendary full-art land

`Gaea's Cradle` remains a full-art Generic Showcase land and uses the floating neutral land legendary crown treatment. Green identity comes from its pinline/rules treatment rather than a normal green permanent frame.

### Basic lands

`Forest`, `Mountain`, `Swamp`, `Plains`, and `Island` use the full-art Generic Showcase land treatment and the **common** Doctor Who set symbol.

## Set-symbol rule

Every card uses the Doctor Who custom set symbol matching its Scryfall/original printed rarity. Do not substitute another rarity icon.

Current rarity files are `mythic.png`, `rare.png`, `uncommon.png`, and `common.png` under `doctor_who/set_icon/`.

## Artwork updates

Artwork and card-data framing are separate concerns.

- Replacing an approved art image normally means replacing the PNG at the same numbered filename; it should not require rebuilding the frame recipe.
- Do not stretch source art to fit. Use the correct frame's `artBounds`, `artX`, `artY`, and `artZoom` as described in the root rules.
- Preserve approved hand crops unless the user asks for a new fit or the crop is demonstrably wrong.
- Do not generate or edit artwork during card-data work unless the user explicitly requests image work.

## Doctor Who validation checklist

Before calling a Doctor Who card-data update complete:

- `doctor_who_cards.cardconjurer` contains exactly 51 unique face entries for the current list
- the ordered keys match the intended 50-slot list with both Esika faces inserted together
- every art URL points to an existing file in `doctor_who/art/`
- every set-symbol URL points to an existing rarity file in `doctor_who/set_icon/`
- all saved cards use the `2010 × 2814` canvas
- current Scryfall mechanics and rarities are reflected correctly
- ordinary enchantments use Nyx where appropriate
- legendary permanents have the correct crown, and nonlegendary cards do not gain crowns from rarity alone
- `The Fourteenth Doctor` uses the native TARDIS (WHO) package
- `Esika, God of the Tree` and `The Prismatic Bridge` use proper Modal DFC front/back treatments, with Nyx on the Bridge
- `RMS Titanic` uses Vehicle framing
- `K-9, Mark I` uses the artifact-creature/blue-identity treatment
- full-art lands use Generic Showcase framing
- every three-color land contains both Middle Third and Right Half masks so all three colors are represented
- footer remains `ChatGPT` / `Custom Proxy • Personal Use Only`
- temporary workflows/build payloads used for large-file generation are removed afterward

If a Doctor Who-specific rule becomes useful to all projects, generalize it into `../STYLE_RULES.md` instead of duplicating it here.
