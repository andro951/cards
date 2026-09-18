# 1-click GitHub setup import

At the top of **Art & setup**, paste a public GitHub **project folder** link and click **1-click import**. The importer fills the existing setup controls in one operation. Review the previews, then use **Save changes** or **Save & generate images**. It does not replace the deck list, selected printings, per-face overrides, credits or templates. The project link is remembered when the setup is saved.

```text
folder/
├── art/                     # Optional: live GitHub card artwork
│   ├── sol_ring.png
│   └── command_tower.png
├── set_symbols/             # Optional override: all four rarity images
│   ├── common.png
│   ├── uncommon.png
│   ├── rare.png
│   └── mythic.png
├── set_symbol.png           # Alternative: color-shift into four (not recommended)
├── back.png                 # Optional: complete custom back
└── back_icon.png            # Optional: icon centered on the blank forge back
```

Set-symbol files are optional. With neither `set_symbols/` nor `set_symbol.png`, the bundled common/uncommon/rare/mythic defaults are selected. Providing either is an intentional override: `set_symbols/` wins over `set_symbol.png`; the older folder name `set_symbol/` is also accepted internally. A present but incomplete, duplicated or invalid symbol folder fails clearly rather than silently falling back. Non-image notes files are ignored. PNG, JPEG, WebP and GIF work; for this importer, export SVGs as PNG or upload them individually using the existing controls.

If `art/` is absent, the importer selects **Scryfall printing**. Scryfall fallback is enabled on import, including when an art folder is present. GitHub artwork stays live and is fetched during generation, not downloaded wholesale on import. Symbols and backs are copied on each import, bypassing the local HTTP cache; import again to update them.

A complete `back.png` takes priority over `back_icon.png` when both exist. An icon uses the existing proportional, transparent-safe forge-back composition. With neither, the default Bulk Proxy Forge back is selected. Individual back overrides, real double-faced reverses and meld backs keep their existing priority. Import failures and cancellation leave the current setup draft and saved deck unchanged; the eventual save still uses the existing revision/conflict checks.

