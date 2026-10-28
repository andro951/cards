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

### Complete deck recipes (version 2)

Use **More → Export complete data.json** on a finished deck to download its complete recipe. **Save complete data.json** uses the existing connected GitHub/local file or offers connection and download choices. Save again after changing the deck to update that recipe. Artwork/rules/approval save flows also write the complete format.

To rebuild the deck on another computer, choose **Add New Deck → Other import methods** and upload the file. A version-2 file imported through Art & Setup also creates a separate deck. Existing decks and templates are preserved.

The recipe includes the full ordered deck list and quantities, exact printing metadata, all deck settings, per-face edits and crop/position settings, selected frames and custom templates, backs and symbols, token treatments and pairings, alternate-art allocations, warning approvals, notes, and prepared layouts. It records the renderer pipeline and native renderer commit. New workspace identifiers are allocated during import; printing identifiers and rendering inputs remain unchanged.

There are **no embedded images or finished PNGs**. The `images` map identifies source images by SHA-256 and permanent HTTPS location. GitHub image URLs are pinned to commits. Transparent-padding normalization and generated icon backs are recorded as build operations. Bundled symbols and backs point to their versioned application assets. User-uploaded art, custom frames, and generated assets without reusable sources require permanent URLs before export; the app previews each missing image and verifies its URL against the saved pixels.

Import validates image hashes and dependencies before publishing the new deck. Missing or changed sources produce an error rather than substituted artwork. Unchanged imported recipes reuse their captured metadata and prepared layouts when **Generate images** rebuilds their PNGs. Editing the recipe's cards/settings returns that deck to the ordinary preparation flow. A recipe from an incompatible renderer pipeline must be rebuilt using its recorded release; the app does not silently migrate it.

The complete format is a JSON object with `version: 2`, `format: "bulk-proxy-forge-deck"`, a `deck` snapshot, `templates`, `images`, `renderer`, and `includesRenders: false`. The top-level `cards`, `artist`, `tokenAssignments`, `tokenTreatments`, and `artVariants` remain compatible with artwork editing and concurrent data-file merges. The file limit is 20 MB. Credentials, browser handles, HTTP/font caches, unrelated decks, and saved print-order ZIPs are not part of a deck recipe.

### Artwork overlays (version 1)

Existing version-1 files remain supported as partial artwork/rules overlays. They cannot recreate a complete deck by themselves. Saving a complete recipe upgrades the file while preserving its other card entries.

Optional top-level `artist` sets the deck artist for custom artwork. Per-card
`artist` values override it. Omitting the top-level field keeps the current deck
artist; an empty string clears it. This works for local files, GitHub file links
and 1-click imports.

The importer checks the project root for `data.json`. The same file may instead be selected from the computer or linked directly as a GitHub `data.json` file in Art & Setup.

```json
{
  "version": 1,
  "artist": "Deck Artist",
  "cards": [
    {
      "name": "Syr Gwyn, Hero of Ashvale",
      "nickname": "Test Commander Nickname",
      "flavor_text": "Custom flavor text.",
      "oracle_text": "Vigilance\nEquip abilities you activate cost {1} less to activate.",
      "artist": "Artist Name"
    }
  ]
}
```

Select a card by exact face `name`, `oracle_id`, or `scryfall_id`; supplied selectors must all match. The other fields are optional; empty values do not erase an existing override. A nickname adds the alternate title and real-name treatment. A nickname exactly equal to the face name is treated as absent; capitalization differences remain distinct. The `artist` field supplies the credit for matching custom art. An `art` field can name any exact image filename in the artwork folder. The [artwork helper and save options](ARTWORK_MATCHING.md) resolve missing or ambiguous images and retain manual mappings for reuse. Invalid JSON or unmatched selectors fail before setup is saved.

Rules-text self-name replacement gives full names priority, then supports comma-prefix names, Planeswalker names, and first-word abbreviations such as `Loran`. Short matches use the nickname before its first comma, or the whole nickname when it has no comma. Generic first words such as `The`, `A`, `Brutal`, colors, card types, and common titles are excluded from first-word guessing. Matching uses whole words and preserves protected longer card names.

`oracle_text` overrides the selected face's displayed rules before formatting and text fitting. Use `\n` for new paragraphs and normal mana notation such as `{T}` or `{1}{U}`. It accepts up to 20,000 characters. An explicit empty `oracle_text` restores the selected official rules; removing a previously imported GitHub override also restores those rules unless it has since been edited locally. Cached Scryfall metadata stays unchanged.

In a card's editor, open **Artwork positioning & text overrides**, edit **Rules text override**, then choose **Save**. Changed rules are saved to the deck and automatically written to a connected GitHub file or accessible local file/folder. Without a connection, Save offers GitHub or local-file connection, or a data.json download. A newly connected GitHub file is retained as the deck's data source for future generation checks. Saving already synchronized rules does not write the file. Updates preserve other entries and fields and check concurrent changes before writing. GitHub saves bypass cached file responses and retry version conflicts up to twice, rereading and checking edited fields each time. Unrelated concurrent changes are merged; a conflicting edit to the same field still stops the save. A failed connected update keeps the editor open so you can retry; the deck edit is retained and Save also detects an unsynchronized local rules edit after reopening the editor.
