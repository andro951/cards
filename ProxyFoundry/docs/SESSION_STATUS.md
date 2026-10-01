# Bulk Proxy Forge browser repair status

Updated 2026-10-01. The current application is the static browser website. Double-click `START_BULK_PROXY_FORGE.bat` for local preview. `START_PROXY_FOUNDRY.bat` retains the old local application.

## Current behavior

- Normal Look and Customize Look gather setup before Generate Images. Normal Look resets custom defaults and uses ordinary frames for lands as well as other ordinary cards.
- Frame and source choices are immediately selectable static card-back placeholders. Importing metadata shows progress and supports cancellation; it does not render or fetch artwork.
- Browser jobs return promptly, report progress, cancel at checkpoints, and preserve completed work across reload. Previous renders remain visible when edits make them stale.
- Binary files live directly in browser-managed storage or the chosen workspace folder. SQLite snapshots persist metadata. Folder reconnection is explicit, and a single writer tab owns a workspace.
- Reusable template v3 supports native structural slots, checked geometry formulas, conditional variants, portable assets, and explicit validation previews before saving.
- The static build supports GitHub Pages repository paths. Publishing is a separate manual workflow; these repairs do not publish the website.

See [browser operation and recovery](BROWSER_WEBSITE.md), [template model](TEMPLATE_MODEL.md), [test policy](TESTING.md), and [audit repair reconciliation](../audit-notes-2026-09-30/12_repair_status.md).

## Verification

The latest routine run passed 503 tests with no skips in the selected group. Six Node adapter/helper tests and JavaScript syntax checks passed. Real static Chromium tests cover import/setup/generation/review/export/reload under `/cards/`, explicit template validation, job cancellation, version mismatch handling, and storage permission/quota/recovery scenarios. The separate 100-image stress test is recorded in the final verification report when it finishes.

Historical v58 integration evidence is in `CARD_TOOLS_V58_UPDATE.md`. The pinned Card Tools vendor verifier still passes; vendor code was not duplicated or modified for these repairs.