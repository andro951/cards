# 1-click GitHub setup import

At the top of **Art & setup**, paste a public GitHub **project folder** link and click **1-click import**. The importer fills the existing setup controls in one operation. Review the previews, then use **Save changes** or **Save & generate images**. It does not replace the deck list, selected printings, per-face overrides, credits or templates. The project link is remembered when the setup is saved.

```text
folder/
├── art/                     # Optional: live GitHub card artwork
│   ├── sol_ring.png
│   └── command_tower.png
├── set_symbols/             # Recommended: all four rarity images
│   ├── common.png
│   ├── uncommon.png
│   ├── rare.png
│   └── mythic.png
├── set_symbol.png           # Alternative: color-shift into four (not recommended)
├── data.json                # Optional: nickname / flavor metadata
├── back.png                 # Optional: complete custom back
└── back_icon.png            # Optional: icon centered on the blank forge back
```

Only the symbols are required: provide the complete four-image folder **or** the single source image. `set_symbols/` wins over `set_symbol.png`; the older folder name `set_symbol/` is also accepted internally. A present but incomplete, duplicated or invalid symbol folder fails clearly rather than silently falling back to generated colors. Non-image notes files are ignored. PNG, JPEG, WebP and GIF work; for this importer, export SVGs as PNG or upload them individually using the existing controls.

If `art/` is absent, the importer selects **Scryfall printing**. Scryfall fallback is enabled on import, including when an art folder is present. GitHub artwork stays live and is fetched during generation, not downloaded wholesale on import. Symbols and backs are copied on each import, bypassing the local HTTP cache; import again to update them.

A complete `back.png` takes priority over `back_icon.png` when both exist. An icon uses the existing proportional, transparent-safe forge-back composition. With neither, the default Bulk Proxy Forge back is selected. Individual back overrides, real double-faced reverses and meld backs keep their existing priority. Import failures and cancellation leave the current setup draft and saved deck unchanged; the eventual save still uses the existing revision/conflict checks.



## Optional `data.json`

The 1-click importer checks the project root for `data.json`. If the file is absent, import works exactly as before. If present, it must use schema version 1:

```json
{
  "version": 1,
  "cards": [
    {
      "name": "Isshin, Two Heavens as One",
      "nickname": "Dean Winchester",
      "flavor_text": "Saving people, hunting things. The family business."
    },
    {
      "name": "The Prismatic Bridge",
      "flavor_text": "Custom flavor text."
    }
  ]
}
```

`name` is required and must exactly match a card face in the current deck. `nickname` and `flavor_text` are optional. Missing values and empty strings are ignored, so an empty field never clears an existing override. A nonempty nickname activates the automatic nickname/Godzilla treatment. A nonempty flavor string overrides that face's resolved Scryfall flavor text.

Like the art/symbol/back setup, `data.json` is **staged** by 1-click import. The saved deck is not changed until **Save changes** or **Save & generate images** is clicked. Invalid JSON, duplicate nonempty entries, unsupported fields, or nonempty names that are not in the deck fail the import without partially applying the bundle.
