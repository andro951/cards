# Source map and interactions

| Area | Entry points and handoff |
| --- | --- |
| Launch and HTTP | `run.py` → `foundry/server.py:App,Handler` → `site/index.html` |
| Deck import | `site/deck.js:importDeck` → `/api/decks/import` → `Workspace.create` → `Sources.import_deck` |
| Art & setup | `site/setup.js:renderSetup` → `/api/decks/{id}/save` → `Workspace.save/validate_settings` |
| One-click bundle | `site/github-setup.js:mountGithubSetupImport` → `/api/setup/github-import` → `github_setup.import_github_setup/parse_card_data_json` → staged `cardData` → `Workspace._apply_card_data` |
| Per-face edits | `site/deck.js` inspector → `Workspace.mutate_card` → `semanticOverrides`, `templateOverride`, art and fit |
| Compilation | `Workspace._prepare_card_faces` → `Compiler.compile_face` → vendored `native.build_one` → frame color → nickname treatment → render key |
| Token conversion | Native Scryfall token: `compiler.build_token_data`. Copy/deck-wide token: `Workspace._apply_token_spec` → `vendor/card_tools/tools/make_copy_tokens.py:build_token` |
| Template choices | `compiler.BUILTINS`, `domain.GROUP_LABELS/type_group`, `site/setup.js:templateOptions`, `site/templates.js` |
| Browser render | `site/render.js` → `/api/runtime/prepare` and render sessions → `runtime.py` iframe → `site/runtime-bridge.js` → `Workspace.save_render` |
| Persistence and output | `storage.Store`, `orders.Orders`, `backup.Backups`, `transfer_batches.TransferBatches`, `extension/` |

The repository root also contains project art/card files, scripts, `templates/` and `testing/`. The application source is contained in `ProxyFoundry/`; its vendored Card Tools source is guarded by `scripts/verify_vendor.py`. The root `STYLE_RULES.md` describes card-data and CardConjurer conventions for project content.
