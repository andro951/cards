# Proxy Foundry

Local-first MTG deck, artwork, template and print-order workspace.

## Integration contract

- Preserve the Card Tools v48 compiler and token/image tools unchanged under `vendor/card_tools`.
- Use the actual pinned CardConjurer renderer; download only referenced runtime files/assets, never repository archives.
- Keep Proxy Foundry open while rendering and when opening TCGPlaytest in a new tab.
- Use explicit FRONT/BACK filename pairs for every physical card and combined multi-deck order.
- Store decks and renders transactionally outside the extracted application folder.
- Accept Scryfall deck links, deck exports and pasted decklists; preserve the selected printing.
- Accept a GitHub artwork folder or a computer folder without converting local paths into GitHub paths.
- Default Scryfall cache age is one year; Fetch new data reduces it to one week, not zero.
- Built-in template geometry is preserved. Explicit template overrides are separate, validated operations.
- Warn when artwork loses more than 20 percent of its width or height to its selected art window.
- Require four rarity symbols, or explicitly generate four treatments from one uploaded symbol.
- Support per-deck/per-card artist credit, DFC backs, copy tokens, custom template import, render caching, backups and combined orders.

## Work in progress

This directory is being built with implementation and regression/smoke tests saved in checkpoints. Existing repository files outside this directory are not modified by the application.
