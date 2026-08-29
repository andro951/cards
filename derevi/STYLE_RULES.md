# Derevi project rules

Read `../STYLE_RULES.md` first. That root file contains the repository-wide Card Conjurer rules, frame-discovery method, standard geometry, Auto Fit method, footer convention, land recipes, and shared tooling. This file contains **Derevi-specific** details only.

## Project source of truth

- Project folder: `derevi/`
- Card Conjurer file: `derevi/derevi_cards.cardconjurer`
- Art folder: `derevi/art/`
- Set-symbol folder: `derevi/set_symbol/`
- Scryfall deck/checklist: `https://scryfall.com/@andro951/decks/cac4a3fa-84f8-4b8e-b946-0d8a8086fd9d`
- Checklist file: `derevi/scryfall_proxy_decklist.txt`
- Derevi itself is an intentional project extra beyond the fetched checklist.
- `PROXY_SYNC_STATUS.md`, `SCRYFALL_RULES_AUDIT.md`, `ART_FIT_AUDIT.md`, and `scryfall_current_cards.json` are useful snapshots but can become stale. Fresh Scryfall data wins.

At the start of a Derevi update, fetch the live repository tree, `../STYLE_RULES.md`, this file, and `derevi_cards.cardconjurer`.

## Derevi asset paths

New/current raw art URL pattern:

`https://raw.githubusercontent.com/andro951/cards/main/derevi/art/<filename>.png`

Set symbols:
- Mythic: `https://raw.githubusercontent.com/andro951/cards/main/derevi/set_symbol/mythic.png`
- Rare: `https://raw.githubusercontent.com/andro951/cards/main/derevi/set_symbol/rare.png`
- Uncommon: `https://raw.githubusercontent.com/andro951/cards/main/derevi/set_symbol/uncommon.png`
- Common: `https://raw.githubusercontent.com/andro951/cards/main/derevi/set_symbol/common.png`

Preserve existing asset filenames, including historical typos such as `savana.png` and `pyrexian_altar.png`, unless the card data is updated in the same change.

The old bottom wings emblem is intentionally not part of the current card design. Do not restore it.

## Derevi standard-card presentation

Ordinary cards use the repository root's standard M15 baseline geometry and footer convention unless a card's real layout requires another Card Conjurer frame.

- Enchantments use the Nyx treatment described in the root rules.
- Legendary permanents use the appropriate M15 crown unless a special frame defines a different legendary treatment.
- Preserve user-approved/manual art placements; recalculate only for new/bad art placement or when explicitly requested.

## Derevi lands

The current special land cycle is:

- `Savannah` — true-borderless Generic Showcase G/W
- `Tropical Island` — true-borderless Generic Showcase G/U
- `Tundra` — true-borderless Generic Showcase W/U
- `Gaea's Cradle` — true-borderless Generic Showcase legendary land with the floating neutral Land Legend Crown

These use the repository-wide **full art land — “no” frame** recipes in `../STYLE_RULES.md`.

For the three duals:
- title/type use the neutral Generic Showcase land treatment
- rules panel is split between the two land colors
- one-line mana reminder text is italic and centered
- keep the neutral Generic Showcase land `Border` mask for the solid black bottom/footer

For Gaea's Cradle:
- use the neutral floating land crown, not the green floating crown
- do not use `Legend Crown Border Cover`
- keep the crown outline and lower cutout treatment
- keep the neutral Generic Showcase land `Border` mask for the same black bottom/footer as the duals
- green identity comes from the pinline/rules treatment
- Oracle rules text remains left-aligned

## Derevi set-symbol rule

Every card uses the Derevi custom set symbol matching its intended/original printed rarity. Do not substitute another rarity icon.

The baseline set-symbol placement is inherited from `../STYLE_RULES.md`.

## Derevi Scryfall refresh

The reusable fetcher now lives at repository root:

`python fetch_scryfall_deck.py --deck-id cac4a3fa-84f8-4b8e-b946-0d8a8086fd9d --output-dir derevi`

The workflow `.github/workflows/fetch-derevi-scryfall.yml` calls that common helper.

Do not recreate a Derevi-only copy of the fetch script.

## Derevi validation checklist

Before calling a Derevi update complete:

- every expected project art file exists under `derevi/art/`
- card-data art URLs point to the current `derevi/art/` structure
- set-symbol URLs point to `derevi/set_symbol/`
- card keys are unique
- current Scryfall mechanics are reflected correctly
- legendary/nonlegendary crown status is correct
- enchantments use Nyx where appropriate
- special layouts use their actual Card Conjurer treatment
- visible text has no unsafe punctuation/replacement glyphs
- footer remains `ChatGPT` / `Custom Proxy • Personal Use Only`
- temporary workflows/scripts used for a large-file update are removed afterward

If a Derevi-specific rule becomes useful to all projects, move/generalize it into `../STYLE_RULES.md` rather than duplicating it here.

## White borderless-land readability override

For Derevi's true-borderless Generic Showcase lands, a white Rules-panel fill keeps the normal white frame asset but uses **`opacity: 85`**. Do not recolor the white asset and do not lower the opacity of the white pinline. This is specifically a Rules-panel readability adjustment for white text over white-associated translucent fills.

All Derevi land rules text is vertically centered. Sparse mana reminder text remains horizontally centered; ordinary Oracle rules text remains left aligned.

## Compact sparse dual-land boxes

`Savannah`, `Tropical Island`, and `Tundra` contain only the parenthetical mana reminder, so they use the repository compact-borderless hybrid: Generic Showcase full-art/title/footer with only the M15 Extended Art Shorter Textbox lower-box masks/assets. Do not add the short package's `frame.svg` or conventional outer border. Their reminder line is centered horizontally and vertically.

`Gaea's Cradle` has real Oracle/flavor text and remains on the normal Generic Showcase lower box.
