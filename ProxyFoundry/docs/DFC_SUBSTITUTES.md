# Double-sided card substitutes

Art & setup → Other Options → **Create double-sided card substitutes** is on by default for each deck, including older decks without an explicit value. It can be turned off independently of token settings. The setting is `createDfcSubstitutes`.

Every playable physical double-sided card gets one additional single-sided substitute per imported copy. Real tokens, token-treated cards, and Day/Night helpers do not get substitutes. Meld component cards with a physical meld reverse are included. Split/adventure/flip cards printed on one surface do not qualify.

The substitute retains the original front's name, mana cost, rules, nickname, and normal frame. Full-art fronts fall back to an ordinary M15 frame (or the native enclosed structural frame for types such as planeswalkers). The bundled wooden sign fits completely inside the art window using contain, with no cropped instructions. A substitute always has the deck's normal card back, falling back to the built-in normal back when the deck explicitly omits backs. Its original double-sided card keeps its original reverse.

Battle substitutes retain the native landscape frame and fit the entire sign between the title and type bars. Their background art bounds normally extend behind those bars, so substitutes use a smaller visible art window.

The bundled 7:5 clay wall fills the full card behind the sign and normal frame. It scales to the card's full height and stays centered horizontally: landscape Battles fit exactly, while portrait cards crop the left and right sides. The sign is an independent native frame layer fitted inside the visible art well, so its instructions are never cropped. Both assets are ingested once per workspace and reused; no per-card composite bitmap is encoded during preparation. This revision refreshes substitutes only, keeping original card renders cached. CardConjurer exports embed both images and backups preserve them.

## Storage and generation

- `card.faces` remains the actual imported front/back pair. `card.substitute` holds the generated face and records its source render key and substitute version. It does not enter art matching, Scryfall metadata lookup, or token pairing.
- `substitutes.render_faces()` includes active generated faces for rendering, final commit validation, and exports. `stored_faces()` includes them for portable backups.
- An unchanged substitute is reused. Missing substitutes on an otherwise cached deck are derived from the cached original fronts; original faces and metadata are reused. Copies share one rendered substitute image. Quantity and back-only changes do not compile or render the fronts again.
- Enabling this option does not change the originals' preparation fingerprints or global pipeline version. The extra rendered face per double-sided card is intentional; decks with no qualifying cards get no additional render targets.
- Substitutes participate in the existing atomic browser generation transaction. Missing or failed substitute renders block final commit. Abort restores the prior deck and render mappings.
- Card grids show substitutes separately, with copy counts and normal-back hover previews. Print orders, image review exports, CardConjurer exports, and backups include them.

The focused tests are `tests/test_dfc_substitutes.py`. Browser cases cover a native render and the production static browser's complete generation/reuse path. Offline DOM tests verify the per-deck checkbox and searchable substitute grid. Test workspaces are isolated from the user's workspace database.
