# Instructions for Creating Card-Data JSON


# Preferred workflow: build directly from a Scryfall deck URL

When the user provides a public Scryfall deck URL, prefer the fully automated
deck pipeline instead of manually looking up every card.

Use:

```bash
python scryfall_deck_to_cardconjurer.py \
  "https://scryfall.com/@USER/decks/DECK_UUID" \
  --project PROJECT_FOLDER
```

Example for the Derevi project:

```bash
python scryfall_deck_to_cardconjurer.py \
  "https://scryfall.com/@andro951/decks/cac4a3fa-84f8-4b8e-b946-0d8a8086fd9d" \
  --project derevi
```

If the command is run from *inside* a project directory that already contains
`art/` and `set_symbol/`, `--project` may be omitted.

The wrapper performs the entire deterministic pipeline:

1. Parse the UUID from the Scryfall deck URL.
2. Request Scryfall's deck JSON export at:
   `https://api.scryfall.com/decks/<UUID>/export/json`
3. Read the deck's `entries` sections and each entry's `card_digest`.
4. Preserve the exact selected Scryfall printing for printing-dependent metadata
   such as rarity.
5. Resolve full Scryfall card data.
6. Save current Oracle rules text.
7. By default, obtain flavor text from the newest English paper printing.
8. Apply any user-provided flavor override instead when one exists.
9. Split Scryfall's type line into semantic source fields:
   `types`, `subtypes`, `legendary`, `basic`, `snow`, and `world` when relevant.
10. Match each card/face to the project's existing `art/` file.
11. Validate the project's rarity image in `set_symbol/`.
12. Write the pure semantic JSON source file.
13. Invoke `card_data_to_cardconjurer.py`.
14. Let that compiler infer all visual recipes and fail on unsupported card
    structures rather than guessing.
15. Write the final `.cardconjurer` file.

The wrapper deliberately leaves the semantic JSON on disk. The JSON is the
human/AI-auditable source of truth; the `.cardconjurer` file is compiled output.

By default, `maybeboard` entries are excluded. Use `--include-maybeboard` if
they should be included. Specific sections can also be selected with repeated
`--section` arguments.

Custom flavor text still has highest priority:

```bash
python scryfall_deck_to_cardconjurer.py \
  "SCRYFALL_DECK_URL" \
  --project derevi \
  --flavor-overrides flavor_overrides.json
```

This deck-URL route requires no AI judgment once the project art, set-symbol
assets, compiler recipes, and any explicit custom flavor overrides are present.
If the compiler encounters an unsupported structural card type, it must fail
and report the card rather than silently choosing a visually similar recipe.

---


## Purpose

These instructions are for ChatGPT or a similar AI creating the **source-data JSON** consumed by `card_data_to_cardconjurer.py`.

The source-data file contains **only semantic card information and project asset names**. It must not contain Card Conjurer frame paths, masks, coordinates, opacities, text-box geometry, font sizes, art bounds, or other visual implementation details.

The intended workflow is:

```text
list of card names
        ↓
current Scryfall data + user flavor overrides + project assets
        ↓
semantic card_data.json
        ↓
card_data_to_cardconjurer.py
        ↓
final .cardconjurer file
```

`layout` is an **optional manual override only**. Do not add it to ordinary entries. The compiler is responsible for deciding the visual recipe from `types`, `subtypes`, `legendary`, `basic`, `snow`, colors, and the other semantic fields.

---

## 1. Required project structure

The card project should have one root folder, such as:

```text
derevi/
  art/
    derevi_empyrial_tactician.png
    spellseeker.png
    ...
  set_symbol/
    common.png
    uncommon.png
    rare.png
    mythic.png
```

The JSON should use the project root to build common raw GitHub paths in `defaults`:

```json
{
  "schema_version": 2,
  "defaults": {
    "repo": "andro951/cards",
    "branch": "main",
    "artist": "ChatGPT",
    "art_base_url": "https://raw.githubusercontent.com/andro951/cards/main/derevi/art/",
    "set_symbol_base_url": "https://raw.githubusercontent.com/andro951/cards/main/derevi/set_symbol/"
  },
  "cards": []
}
```

Each card then normally stores only its art filename, for example:

```json
"art": "spellseeker.png"
```

Do not repeat full art URLs or set-symbol URLs on every card unless there is a genuine exception.

---

## 2. Scryfall is the mechanical source of truth

For every requested card, look it up on Scryfall. Do **not** rely on model memory for current Oracle wording, mana cost, type information, colors, power/toughness, loyalty, defense, or rarity.

Prefer exact-name lookups. If the user supplies a specific Scryfall card-page URL, use that exact printing as the printing reference.

For mechanical text, save the current Scryfall **Oracle text**, not printed text from an old printing.

### Flavor text

Flavor text is printing-specific, unlike Oracle rules text.

Use this precedence:

1. If the user supplied replacement flavor text for the card or face, use the user's text.
2. Otherwise, if the user supplied a specific Scryfall printing URL, use the flavor text on that printing.
3. Otherwise, for a name-only lookup, use the newest English paper printing's flavor text when available.
4. If no applicable Scryfall printing has flavor text, omit `flavor_text` rather than inventing one.

Never rewrite Scryfall's Oracle text. Never invent missing flavor text unless the user specifically asks for newly written flavor.

---

## 3. The JSON must use semantic type fields

**Do not put `type_line` in the source JSON.**

The compiler constructs the displayed type line itself.

For every card or face, split Scryfall's current type line into:

- `types`: list of all main card types.
- `subtypes`: list of all subtypes after the dash.
- `legendary`: `true` or `false`.
- `basic`: `true` or `false`.
- `snow`: `true` or `false`.
- `world`: include only when true; otherwise it may be omitted.

Main types recognized by the current semantic schema are:

```text
Artifact
Battle
Creature
Enchantment
Instant
Kindred
Land
Planeswalker
Sorcery
Tribal   (legacy/custom compatibility only)
```

Examples:

`Legendary Creature — Bird Wizard`

```json
"types": ["Creature"],
"subtypes": ["Bird", "Wizard"],
"legendary": true,
"basic": false,
"snow": false
```

`Enchantment Creature — Cat Glimmer`

```json
"types": ["Enchantment", "Creature"],
"subtypes": ["Cat", "Glimmer"],
"legendary": false,
"basic": false,
"snow": false
```

`Artifact Creature — Construct`

```json
"types": ["Artifact", "Creature"],
"subtypes": ["Construct"],
"legendary": false,
"basic": false,
"snow": false
```

`Basic Land — Forest`

```json
"types": ["Land"],
"subtypes": ["Forest"],
"legendary": false,
"basic": true,
"snow": false,
"land_colors": ["G"]
```

The order of `types` and `subtypes` should follow the current Scryfall type line.

---

## 4. Required card fields

Every ordinary entry should contain:

```json
{
  "name": "Spellseeker",
  "mana_cost": "{2}{U}",
  "types": ["Creature"],
  "subtypes": ["Human", "Wizard"],
  "legendary": false,
  "basic": false,
  "snow": false,
  "oracle_text": "When this creature enters, you may search your library for an instant or sorcery card with mana value 2 or less, reveal it, put it into your hand, then shuffle.",
  "colors": ["U"],
  "art": "spellseeker.png",
  "rarity": "rare",
  "flavor_text": "Not content with mere answers, she hunts for the truth.",
  "power": "1",
  "toughness": "1"
}
```

### Field rules

#### `name`
Use the current Oracle card/face name from Scryfall.

#### `mana_cost`
Use Scryfall's current mana-cost string. Use `""` for cards with no mana cost.

#### `types`
All main types from the current Scryfall type line, excluding supertypes such as Legendary or Basic.

#### `subtypes`
All subtypes after the type-line dash, in order. Use `[]` if there are none.

#### `legendary`
Boolean derived from the current Scryfall type line.

#### `basic`
Boolean derived from the current Scryfall type line.

#### `snow`
Boolean derived from the current Scryfall type line.

#### `world`
Boolean. Include only for World permanents if applicable.

#### `oracle_text`
Current Scryfall Oracle text exactly as Scryfall provides it. Preserve line breaks. Do not combine flavor text into this field.

#### `flavor_text`
User override if one was supplied; otherwise the applicable Scryfall flavor text. Omit the field if there is no flavor text.

#### `colors`
Use Scryfall's **card colors**, not color identity. Values may only be `W`, `U`, `B`, `R`, `G`. Colorless cards use `[]`.

#### `power` and `toughness`
For creatures and Vehicles that have P/T, store each as a string. Preserve values such as `*`, `1+*`, etc. Do not pre-combine them into a display string.

#### `loyalty`
If Scryfall supplies loyalty, preserve it as a string. The current Card Conjurer compiler may still reject Planeswalkers until a supported layout recipe exists.

#### `defense`
If Scryfall supplies Battle defense, preserve it as a string. The compiler may still reject Battles until a supported recipe exists.

#### `rarity`
Use the Scryfall printing rarity unless the user specified a different intended rarity. The standard project symbol folder currently expects:

```text
common
uncommon
rare
mythic
```

If Scryfall reports a nonstandard rarity such as `special` or `bonus`, do not silently map it. Ask for or use an explicit rarity override.

#### `art`
Use the filename of the art already stored under the project's `art/` folder. Preferred naming is lowercase snake_case, for example `derevi_empyrial_tactician.png`.

Do not invent an art URL when the project already has the file.

---

## 5. Land color data

Land cards are normally colorless in Scryfall's `colors` field, so the compiler also needs semantic mana/color information for choosing the land treatment.

Add `land_colors` for lands when a color treatment can be determined.

Determine it in this order:

1. Basic land subtypes (`Plains=W`, `Island=U`, `Swamp=B`, `Mountain=R`, `Forest=G`).
2. Scryfall `produced_mana` when available.
3. Basic land types named in the Oracle text, which is especially important for fetch lands.
4. Explicit `{W}`, `{U}`, `{B}`, `{R}`, `{G}` mana symbols in the land's Oracle text.

Examples:

```json
"types": ["Land"],
"subtypes": ["Forest", "Plains"],
"land_colors": ["G", "W"]
```

```json
"name": "Flooded Strand",
"types": ["Land"],
"subtypes": [],
"land_colors": ["W", "U"]
```

Do not use Commander color identity as a substitute for `land_colors`.

---

## 6. `layout` is optional and should normally be absent

For the overwhelming majority of entries, **do not include a `layout` key at all**.

The compiler should infer the visual construction from the semantic fields. For example:

- `types=["Creature"]` + `legendary=false` → normal creature construction.
- `types=["Creature"]` + `legendary=true` → normal legendary creature construction.
- `types=["Enchantment"]` → Nyx/enchantment construction.
- `types=["Enchantment","Creature"]` → enchantment/Nyx frame combined with the creature P/T treatment.
- `types=["Artifact","Creature"]` → artifact creature construction.
- `types=["Land"]` + `basic=true` → basic full-art land construction.
- `types=["Land"]` + two `land_colors` → two-color full-art land construction.

Only include `layout` when there is a previously approved special visual treatment that cannot be inferred from semantic card data.

Never use `layout` merely to avoid fixing the type-inference rules.

If a card has an unsupported structural type/layout and no approved override exists, **fail and report the card**. Do not choose the closest-looking template.

---

## 7. Multi-face cards

Scryfall may return `card_faces` for transform cards, Modal DFCs, meld cards, and other multi-face structures.

For source-data purposes:

- Create one semantic entry per physical face.
- Use the face's own `name`, `mana_cost`, type data, Oracle text, colors, P/T, loyalty, defense, and flavor text.
- It is acceptable to add semantic relationship metadata such as:

```json
"parent_name": "Esika, God of the Tree // The Prismatic Bridge",
"face_index": 0,
"scryfall_layout": "modal_dfc"
```

Those fields describe the source card relationship; they do not describe Card Conjurer geometry.

Do **not** invent a `layout` override. If the Card Conjurer compiler does not know how to render that multi-face structure, report it as unsupported so a proper template/recipe can be added.

---

## 8. Custom flavor-text overrides

When the user supplies custom flavor text, treat it as authoritative for that card/face.

Example user instruction:

```text
Use "When she falls, another finds their place." for Derevi.
```

Output:

```json
"flavor_text": "When she falls, another finds their place."
```

The current Oracle rules text must still come from Scryfall. A flavor override does not authorize changing mechanical text.

If a custom flavor mapping is provided separately, exact face/card names should be used as keys so there is no ambiguity.

---

## 9. Art and set-symbol validation

Before finalizing the source JSON:

1. Confirm the project root has `art/` and `set_symbol/`.
2. Confirm every JSON `art` filename exists under `art/`.
3. Confirm every used rarity has a matching symbol file under `set_symbol/`.
4. Do not rename existing art merely to make lookup easier unless the user asked for repository cleanup.
5. If multiple art files could match one card, do not guess; require an explicit mapping.

---

## 10. Do not put visual Card Conjurer data in the source JSON

The following belong in `card_data_to_cardconjurer.py`, **not** in `card_data.json`:

- `frames`
- frame image paths
- masks
- `bounds`
- opacity
- frame color implementation
- crown geometry
- title/type/rules coordinates
- P/T oval geometry
- text font sizes
- title-width geometry
- art bounds
- `artX`, `artY`, `artZoom`, `artRotate`
- set-symbol coordinates/zoom
- footer geometry
- watermarks
- Card Conjurer `version`
- arbitrary nested `overrides`

If you find yourself copying a chunk of `.cardconjurer` JSON into the input file, stop. That is the wrong layer.

---

## 11. Recommended automated workflow

When available, use `scryfall_to_card_data.py` rather than manually transcribing Scryfall data.

Example:

```bash
python scryfall_to_card_data.py \
  --project derevi \
  --repo andro951/cards \
  --branch main \
  --list derevi_card_names.txt \
  --flavor-overrides derevi_flavor_overrides.json \
  -o derevi_card_data.json
```

Then audit the compiler's decisions:

```bash
python card_data_to_cardconjurer.py derevi_card_data.json --explain
```

Then compile:

```bash
python card_data_to_cardconjurer.py \
  derevi_card_data.json \
  -o derevi_cards.cardconjurer
```

If either script reports an unsupported structure, missing art, missing set symbol, unknown type, or ambiguous asset mapping, fix that problem explicitly. Do not bypass validation by forcing an unrelated template.

---

## 12. Final AI checklist

Before handing the JSON to the user, verify all of the following:

- Every requested card was found on Scryfall.
- Card order matches the user's source list unless the user requested another order.
- `oracle_text` is current Scryfall Oracle text.
- User-provided flavor overrides were preserved exactly.
- Cards without overrides use the applicable current Scryfall flavor text when available.
- There is no `type_line` field.
- Every entry has a `types` list and `subtypes` list.
- Every entry has explicit `legendary`, `basic`, and `snow` booleans.
- `colors` contains card colors, not Commander color identity.
- Lands have `land_colors` when the compiler needs a colored land treatment.
- Creature P/T is stored as separate `power` and `toughness` strings.
- Art filenames exist in the project `art/` folder.
- Rarity symbol files exist in `set_symbol/`.
- `layout` is absent on normal entries.
- No Card Conjurer geometry or frame JSON leaked into the source-data file.
- Unsupported card structures are reported rather than guessed.


## Existing project flavor text is an automatic override

For an established proxy project, hand-authored flavor text already present in
the project's existing `.cardconjurer` batch must be preserved automatically.

The ingestion script searches the project directory for the conventional file:

`<project>/<project>_cards.cardconjurer`

For example:

`derevi/derevi_cards.cardconjurer`

If that file exists, every string after Card Conjurer's `{flavor}` marker is
treated as project-authored flavor text.

Flavor precedence is:

1. Explicit `--flavor-overrides` JSON supplied for this run.
2. Existing project `.cardconjurer` flavor text.
3. Scryfall flavor text.
4. No flavor text if none exists from any source.

This means regenerating an established project from its Scryfall deck link
must not erase custom flavor that was previously written for the proxy batch.

If the project folder contains multiple `.cardconjurer` files and none matches
the conventional `<project>_cards.cardconjurer` name, the script must fail
rather than guess. Use `--existing-cardconjurer` to select the intended file.

Use `--no-existing-project-flavor` only when the user explicitly wants to
discard existing project flavor and rebuild flavor strictly from Scryfall /
explicit override data.
