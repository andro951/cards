MTG CARD TOOLS LOCAL UI
=======================

Start on Windows:
1. Extract this ZIP.
2. Double-click START_LOCAL_UI.bat.
3. Your browser should open automatically.

The launcher checks for Pillow (used only for special post-download art crops) and installs it automatically if needed.

The app has two tabs.

CARD PIPELINE
-------------
Runs the existing Scryfall -> semantic JSON -> Card Conjurer pipeline.

Current controls include:
- Scryfall deck link
- local project folder
- Include Outside The Game
- Use Scryfall art as fallback (off by default)
  * custom art already present in the configured GitHub project art/ directory ALWAYS wins first
  * Scryfall art_crop is used only for cards that do not have matching custom GitHub art
  * the GitHub art/ directory is listed once per run, so an old local Scryfall cache cannot override newer custom GitHub art
  * Scryfall art is cached separately in the project's scryfall_art/ folder and never overwrites custom art
  * repeated Scryfall-fallback runs reuse the cached Scryfall image instead of downloading it again
  * Saga Creatures with trailing normal creature rules text (for example Flying on Summon: Bahamut) trim 99 px from the top and 83 px from the bottom of the downloaded Scryfall art before use
  * those special cropped art files are cached locally and embedded into the current Card Conjurer output so the crop is actually used
- Fetch new card data (off by default)
  * normal cache lifetime: 1 year
  * when checked, cache entries are refreshed only when at least 7 days old
- missing-art / missing-symbol / auto-fit controls
- universal set-symbol horizontal placement
  * every rendered set symbol ends at 92.13% of card width
  * the symbol left edge is calculated from its actual rendered width
  * overlapping type-line width is derived from the symbol width with a 1% card-width gap
- multicolored Vehicles
  * 2+ color Vehicles use gold/multicolored Title and Type bars
  * the rest of the Vehicle frame treatment remains unchanged

The per-card Scryfall cache is persistent outside this extracted folder so replacing the UI does not erase it.

DOWNLOAD DECK IMAGES
--------------------
Downloads the exact selected Scryfall full-card PNGs, names them using the existing snake_case card_name.png convention, and creates a ZIP.

Important image behavior:
- Uses one Scryfall deck-export request to learn the deck and exact selected printings.
- Uses the direct front/back image URLs already embedded in each deck-export card_digest.
- Does NOT make a separate per-card Scryfall API request just to discover image URLs.
- Actual PNG bytes are downloaded directly from Scryfall's image CDN.
- Commander/nonland/land sections are included by default.
- Sideboard and maybeboard are excluded.
- Outside The Game is off by default and has its own checkbox.
- Double-faced cards save each face under that face's snake_case name.

Outputs are placed under the app's outputs/ folder and the ZIP is offered as a download in the UI.

COPY TOKEN TOOL
---------------
A new helper script is included at:
  tools/make_copy_tokens.py

Purpose:
- Takes an existing .cardconjurer file.
- Appends token-frame copy versions of selected cards.
- Uses the M15 bordered token frame style you settled on.
- Supports type-line modifications such as:
  * nonlegendary = removes only the Legendary supertype.
  * replace_creature_subtypes = replaces only the creature subtype section
    (for example Human Soldier Mercenary -> Illusion), which matches the
    Preston, the Vanisher style of setting a creature type without removing the
    card's other types/supertypes.
- Also supports optional power/toughness override and frame-color override.

Quick usage:
1. Create a spec JSON file.
2. Run:
   python tools/make_copy_tokens.py input.cardconjurer output.cardconjurer --spec token_specs.json

Example spec entry:
[
  {
    "source_name": "Cloud, Midgar Mercenary",
    "token_key_suffix": " — Helm Token",
    "nonlegendary": true
  },
  {
    "source_name": "Some Legendary Creature",
    "token_key_suffix": " — Preston Token",
    "replace_creature_subtypes": "Illusion",
    "power_toughness": "0/1",
    "frame_color": "W",
    "color_override": "white"
  }
]

COPY TOKEN MAKER IN THE UI
--------------------------
The Card Pipeline tab now also contains a Copy Token Maker section.
Choose an existing .cardconjurer file and add one or more token rows.
Each row has:
- Source card name
- Non-legendary checkbox: removes only the Legendary supertype and removes the legendary crown from the token frame
- Type override: replaces creature subtypes only (for example Human Warlock -> Illusion), while keeping card types and supertypes
- P/T override: optionally replaces printed power/toughness (for example 0/1)

Blank type/P/T overrides preserve the copied card's values. Generated tokens use the M15 bordered token frame and include the correct P/T frame object.

STRICT ART VALIDATION UPDATE
----------------------------
- Local art filename lookup now preserves the actual on-disk filename capitalization.
  This prevents Windows case-insensitive paths from producing case-wrong GitHub raw URLs.
- Card Conjurer art auto-fit failures are fatal. If an art URL cannot be loaded or decoded,
  the build stops immediately and reports the card plus the exact art URL that failed.
- Use Disable auto-fit only when you intentionally want to bypass auto-fit entirely.
