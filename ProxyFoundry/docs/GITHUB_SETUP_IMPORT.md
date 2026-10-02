# One-click GitHub setup import

In **Custom → Art & Setup**, paste the link to a public GitHub project folder and choose **1-click import**. The importer stages its art source, four symbols, back, and optional `data.json` for review. **Save changes** applies the staged setup. Template selections and unrelated deck options stay separate.

```text
folder/
├── art/                     # Optional card artwork
│   ├── Sol Ring.png
│   └── command_tower.png
├── set_symbols/             # Optional four rarity images
│   ├── common.png
│   ├── uncommon.png
│   ├── rare.png
│   └── mythic.png
├── data.json                # Optional nickname, flavor, and artist data
├── back.png                 # Optional complete custom back
└── back_icon.png            # Optional icon on the Bulk Proxy Forge back
```

The older `set_symbol/` four-image folder remains accepted. A root-level single `set_symbol.png` is no longer supported. If both back images exist, `back.png` takes priority. If custom art is missing, the import leaves Scryfall fallback **off** by default; the user can turn it on in Artwork. GitHub art stays linked to that public folder and is fetched during generation. Symbols and backs are copied into the user's workspace.

Set symbols may also be imported directly from a public GitHub folder in the **Set Symbols** panel. That folder must contain exactly one image each for common, uncommon, rare, and mythic. The computer-folder path follows the same four-name rule. Invalid, missing, or duplicate rarity images produce an error when imported.

## `data.json`

The importer checks the project root for `data.json`. The same file may instead be selected from the computer or linked directly as a GitHub `data.json` file in Art & Setup.

```json
{
  "version": 1,
  "cards": [
    {
      "name": "Syr Gwyn, Hero of Ashvale",
      "nickname": "Test Commander Nickname",
      "flavor_text": "Custom flavor text.",
      "artist": "Artist Name"
    }
  ]
}
```

Select a card by exact face `name`, `oracle_id`, or `scryfall_id`; supplied selectors must all match. The other fields are optional; empty values do not erase an existing override. A nickname adds the alternate title and real-name treatment. The `artist` field supplies the credit for matching custom art. An `art` field can name any exact image filename in the artwork folder. The [artwork helper and save options](ARTWORK_MATCHING.md) resolve missing or ambiguous images and retain manual mappings for reuse. Invalid JSON or unmatched selectors fail before setup is saved.
