# Card Tools v48 → supplied v54 review (in progress)

Compared the exact `vendor/card_tools` tree from verified Proxy Foundry commit 355f3f4 to the uploaded `MTG_Card_Pipeline_Local_UI_v54(1).zip`. Ignored generated Python bytecode only.

Four distributed source/document files changed: the CardConjurer compiler, Scryfall semantic ingestion, input instructions and README. Six other files are byte-identical: the local UI, Windows launcher, deck importer, original-printing image downloader, copy-token tool and token specification example. The embedded LAYOUTS dictionary is exactly equal between versions; the changes are procedural recipe/postprocessing logic, not a replacement template library.

Meaningful differences identified:

- v54 records the actual Scryfall face artist (falling back to the physical card artist) when using original/fallback art. Explicitly missing artist remains blank instead of becoming the custom project artist.
- Compiler respects a per-card semantic `artist` before the project default.
- Kamigawa Flip cards become one physical output with nested `flip_face`, native shared-art Flip frame, rotated lower text and independent upper/lower P/T pieces. They are not DFC reverses.
- The named Iron Man full-art dual-land exception is removed; it follows the normal legendary artifact-creature recipe.
- Multicolor Vehicles use gold Title and Type bars while retaining their Vehicle frame body/P/T.
- A universal 0.9213 right edge and 0.01 type-line gap use the actual set-symbol dimensions and zoom. Symbols center on the type line. Flip reserves its upper/lower P/T medallions as a deliberate exception.
- Existing Station layering and land-family policies are documented more explicitly, but their existing recipes are not rewritten by these differences.

Integration work will promote the supplied v54 sources byte-for-byte, adapt Proxy Foundry's bypassed ingestion path for nested Flip semantics and actual-art provenance, add a separate optional modification credit, and invalidate old render keys without deleting saved order snapshots. Custom uploaded template geometry will not be silently subjected to the new built-in symbol-placement pass.

Initial credit-resolver checkpoint: 14 local unit tests passed, including original artist preservation despite deck/per-card overrides, per-face precedence, missing metadata, modified custom uploads and suffix inheritance/suppression. UI/native-render tests and final integration are not yet complete.
