# Confirmed implementation gaps and bugs

## P1 — The requested direct `data.json` inputs do not exist

**Evidence:** `site/setup.js` has art and symbol file inputs, GitHub art folder text, and one-click bundle import, but no `data.json` file picker or direct URL control. `server.py` exposes only `/api/setup/github-import` for this schema; `github_setup.py` reads root `data.json` only inside that bundle.

**Impact:** A local `data.json` or standalone GitHub file URL cannot update nicknames/flavor through the intended Art & setup workflow.

**Repair:** Reuse `parse_card_data_json` for both new inputs, stage results alongside the bundle path, and save via the existing `cardData` contract. Test all three paths, bad files, and unsaved cancellation.

## P1 — Deck-wide/copy token conversion discards a compiled nickname frame

**Evidence:** `Compiler.compile_face` calls `apply_nickname_treatment`; later `Workspace._prepare_card_faces` calls `_apply_token_spec` for copy or deck-wide tokens. Vendored `apply_token_layout` assigns a fresh `data["frames"]` list, and sets the title to `#fde367`.

**Impact:** A nickname card converted to a token can keep some nickname text while losing the frame added earlier, and title styling diverges. The exact black-token appearance needs native render confirmation.

**Repair:** Define an explicit token/nickname composition path after token conversion, preserving complete frame pieces and readable text. Test colorless and each color, ordinary and token conversion paths, with pixel inspection.

## P2 — Token type/rules typography lacks the requested white outline treatment

**Evidence:** `compiler.build_token_data` sets `text.title.color='white'` but assigns no color/outline to `text.type` or `text.rules`. The vendored copy-token path likewise changes layout without setting those text colors.

**Impact:** Type and rules may inherit dark text on art; flavor shares the rules box and can suffer the same readability issue.

**Repair:** Use the repository's supported CardConjurer outline/shadow properties for token type, rules and flavor, and verify via native renders. Preserve explicit alternate typography where a structural recipe requires it.
