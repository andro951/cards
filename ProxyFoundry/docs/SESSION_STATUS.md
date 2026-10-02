# Bulk Proxy Forge browser repair status

Updated 2026-10-01. The current application is the static browser website. Double-click `START_BULK_PROXY_FORGE.bat` for local preview. `START_PROXY_FOUNDRY.bat` retains the old local application.

## Current behavior

- Full-art artwork uses centered cover fitting across the entire card canvas, including Godzilla and the original full-art land families. Frame and text overlays retain their native positions. Pipeline v29 invalidates earlier placement results. See [full-art verification](FULL_ART_VERIFICATION.md).

- Deck deletion immediately removes the tile and opens Deck Library after confirmation, with durable background cleanup and failure recovery. Saved print orders block deletion and link to a filtered order list; orders can be reviewed and deleted. Pending requests are scoped to the workspace.

- Normal Look and Customize Look gather setup before Generate Images. Normal Look resets custom defaults and uses ordinary frames for lands as well as other ordinary cards.
- Frame and source choices are immediately selectable static card-back placeholders. Importing metadata shows progress and supports cancellation; it does not render or fetch artwork.
- Browser jobs return promptly, report progress, cancel at checkpoints, and preserve completed work across reload. Previous renders remain visible when edits make them stale.
- Binary files live directly in browser-managed storage or the chosen workspace folder. SQLite snapshots persist metadata. Folder reconnection is explicit, and a single writer tab owns a workspace.
- Reusable template v3 supports native structural slots, checked geometry formulas, conditional variants, portable assets, and explicit validation previews before saving.
- The static build supports GitHub Pages repository paths. Publishing is a separate manual workflow; these repairs do not publish the website.

See [browser operation and recovery](BROWSER_WEBSITE.md), [template model](TEMPLATE_MODEL.md), [test policy](TESTING.md), and [audit repair reconciliation](../audit-notes-2026-09-30/12_repair_status.md).

## Verification

The latest routine run passed 531 tests with no skips in the selected group. Six Node adapter/helper tests and JavaScript syntax checks passed. Real static Chromium tests cover import/setup/generation/review/export/reload under `/cards/`, explicit template validation, job cancellation, version mismatch handling, and storage permission/quota/recovery scenarios. The 100-image stress run saved all 100 with zero errors and retained them after reload. The final build also passes a real native render with memory forced above 2 GiB. See the [verification report](BROWSER_REPAIR_VERIFICATION.md).

Historical v58 integration evidence is in `CARD_TOOLS_V58_UPDATE.md`. The pinned Card Tools vendor verifier still passes; vendor code was not duplicated or modified for these repairs.
Slow network, preparation, storage and rendering operations are recorded in diagnostics; see [timing logs](TIMING_LOGS.md).

Native render saves now validate and preserve original PNG bytes, and unchanged database snapshots are skipped. See [save verification and benchmark](RENDER_SAVE_VERIFICATION.md).

New timing records and the diagnostics summary identify browser versus selected-folder storage.

The real Windows selected-folder save benchmark passed using the user's Documents folder: old full requests averaged 8.187 sec, optimized requests 5.881 sec (28.2% faster). Exact PNG bytes, physical files and reload recovery were verified. See the save verification report for evidence and reproduction.

Save profiling now separates the earlier benchmark's extra verification readback. For a first unique PNG in a real selected folder, render copying (34%), asset persistence (30%), and temporary input staging (24%) dominate. Synchronous filesystem bridge overhead accounts for 59% of total time; validation is only 3.5%. See [save profile](RENDER_SAVE_PROFILE.md). Production behavior is unchanged by this investigation.

The storage bridge bottleneck is now fixed: temporary inputs stay in memory, exact native PNG asset writes reuse request-scoped browser buffers, and render copies stream directly between browser handles. New-image saves measured 0.898 sec in browser storage and 2.321 sec in a real Windows folder, compared with 5.017 and 6.758 sec before. Exact bytes and app reload recovery passed in both modes. Final affected checks passed: 13 browser storage cases, the above-2-GiB native rendering regression, and all 531 then-collected routine tests plus the newly added copy-failure unit test. See save verification for details; the long full-deck stress sweep was not run.
