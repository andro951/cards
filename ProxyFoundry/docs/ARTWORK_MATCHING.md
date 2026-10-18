# Artwork matching and reusable data

## Implementation plan and choices

1. Share Python validation between local files, GitHub imports and deck saves so the same selectors and errors apply everywhere.
2. Build an indexed inventory from filenames and immutable GitHub blob identities. Match explicit filenames, then UUIDs, then unambiguous card names. Never fetch artwork bytes or render cards for this check.
3. Gate generation with a full-screen exception helper. Use Scryfall source card images on the left and unused custom images with filenames on the right. Allow pairing, undo, enlargement, filtering, adding files, resuming and explicit fallback confirmation.
4. Save choices into the deck before generation. Offer a portable JSON download or updating the original source. Retain browser file/directory handles and use browser-only GitHub Contents API requests; no server is introduced.
5. Verify schema errors, token variants, ambiguity, duplicate filenames, merges, permission denial, GitHub SHA conflicts, bounded DOM size, reload persistence and the real static browser route. Run the routine suite and affected extended browser checks.

## Matching

An `art` entry selects an exact filename relative to the selected artwork folder. Oracle IDs identify card variants across printings; a Scryfall printing ID is also accepted when an exact printing is intended. UUIDs may appear anywhere in an image filename. Existing name matching, including numbered prefixes, remains available. Names and UUIDs are selectors, not replacement display names.

```json
{
  "version": 1,
  "cards": [
    {
      "oracle_id": "dc4e2134-f0c2-49aa-9ea3-ebf83af1445c",
      "name": "Spirit",
      "scryfall_url": "https://scryfall.com/card/tst/1/spirit",
      "art": "my-white-spirit.png",
      "artist": "Artist Name"
    }
  ]
}
```

Exported downloads, local file updates, and GitHub updates include a reference entry for every deck face. Entries include the Oracle ID and the selected printing’s `scryfall_url` when Scryfall provides them. The URL is informational and is never used as a matching selector. Records without an Oracle ID use the printing ID. Separate faces retain their names, token variants remain separate, and multiple selected printings of the same card also retain their printing IDs. Existing nicknames, flavor text, artists, artwork mappings, and entries for other decks are preserved.

`name`, `oracle_id`, or `scryfall_id` is required. Supplied selectors must all match. A face name distinguishes two faces sharing an Oracle ID: for Day // Night, use two entries with `name: "Day"` and `name: "Night"`. Automatic UUID filenames for these faces should include `day` or `night`, such as `day_UUID.png` and `night_UUID.png`.

Existing `nickname`, `flavor_text`, and `artist` fields remain supported. UUID-specific entries take precedence over name-only entries; face-specific entries take precedence over whole-card entries. Artwork selectors matching multiple variants or faces are rejected: identify those mappings with a UUID and face name. Missing mapped files and conflicting filename matches are shown for manual resolution, including when fallback is enabled. Distinct token variants cannot silently share a name match. Separate explicit mappings can deliberately reuse an image.

## Review and persistence

**Match custom artwork** opens the helper in Art & Setup. Requesting generation checks the inventory too. Setup edits save automatically without opening the matching helper. No renderer runs during matching. Extra files must be acknowledged; unresolved cards require pairing or the explicit **Default Art for the rest** choice when fallback is enabled. Inventory changes invalidate the acknowledgement. Pending pairs are retained in browser storage; completed choices are persisted in the deck.

The helper initially creates at most 80 card thumbnails and 60 artwork thumbnails. Search and Show more let large folders remain usable. Local paths and original extensions are retained rather than reducing every image to a card-name stem.

## Saving data.json

- A retained local file handle allows updating that file after write permission is granted. A retained artwork directory allows creating `data.json` there. Browsers using ordinary file inputs cannot expose the original writable location; they offer a download.
- Folder selection can discover a root `data.json` and retain its handle. Standalone JSON selection uses the supported browser file picker to retain the original handle.
- GitHub updates use a connection token selected for that repository. Users may remember the connection for future `data.json` updates or use it once. One-update credentials are discarded after the attempt; remembered credentials can be forgotten. GitHub token expiration still applies.
- The GitHub guide uses a [pre-filled token setup link](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#pre-filling-fine-grained-personal-access-token-details-using-url-parameters), a short 90-day expiration reminder, and five annotated screenshots: select the repository, check the selected repository, generate, confirm, and copy. Captions show the actual repository; images can be enlarged. GitHub’s link sets the expiration date but cannot select the repository or the expiration dropdown label. A successful update names the repository, file, and branch in a notification.
- Updates reread the file, preserve existing card metadata, merge only manually paired artwork entries and reject conflicting edits. GitHub writes include the current SHA, following the [GitHub Contents API](https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28). Downloads contain the deck’s combined card data.

GitHub write behavior is tested with API fixtures, including exact request paths and SHA use. A live authenticated write requires the user’s repository connection and is not performed as part of development tests.

Native browser tests retain actual file/directory handles across reload, update an existing JSON file, and create a new one in the retained directory. They use a regular Chromium profile because the private test profile crashes while restoring serialized OPFS handles. Permission denial and the permission-request path are covered by controlled fixtures; no user folders are modified by these tests.
