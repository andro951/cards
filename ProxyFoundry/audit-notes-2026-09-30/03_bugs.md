# Confirmed bugs and requirement gaps

## B1 — High: browser preparation jobs cannot provide live progress/cancellation

Evidence: foundry/browser.py:36 executes operation inline before returning its ID; web/engine-worker.js:44 serializes requests. site/ui.js:100 awaits the start response before showing the job activity/cancel handler. Direct probe order: operation starts -> operation finishes -> start returns job ID; returned job already done. Original foundry/jobs.py submits to a thread pool and returns immediately.

Impact: long import/preparation/export work gives ineffective progress polling and cancellation. Other engine API requests, including diagnostics, wait behind it. This does not imply every JavaScript card-render stage lacks progress.

Repair: early job identity, incremental yielding, progress events, cancellation between work units, separately responsive control requests. Test against the actual static browser engine with a deliberately slow multi-item operation.

## B2 — High: expired folder permission silently switches workspace

Evidence: web/storage-choice.js:23 returns null for a remembered folder without granted permission; engine startup interprets null as browser-managed storage.

Impact: decks can appear missing and new work can land in another workspace. Existing files are not proven deleted. Repair: retain chosen-backend identity, show reconnect state, request permission on user action, switch only explicitly. Test reload with denied/revoked folder permission.

## B3 — Medium: dirty state conflates ordinary edits with global pipeline upgrades

Evidence: foundry/workspace.py:184/188 marks missing compilation upgradeRequired. site/deck.js:258 forces rendering from this flag; site/render.js:72 ORs it across selected decks. Mutations remove compiled state (workspace.py:271/295/364).

Impact: unnecessarily broad regeneration; prior preview can disappear after edits. These patterns are retained/inherited, rather than all newly introduced by the browser port. Repair: separate last render, dirty reason, and real pipeline incompatibility; cache decisions per face/deck. Test one edited face in 100 and two selected decks with only one stale.

## B4 — Medium: Outside-the-game opt-out missing from primary import

Evidence: site/deck.js:85 hardcodes includeOutside:true. Secondary add-card import uses a checkbox and a different default (workspace.py:385).

Impact: cannot exercise the documented opt-out consistently. Repair: collect inclusion choice through the secondary import options and preserve it through Choose Look. Test both values through the primary path.

## B5 — Medium: template editor advertises unsupported token seeds

Evidence: web/templates-browser.js:37 offers Use as starting point on token families; :71 sets group token. foundry/template_model.py rejects conversion outside ORDINARY_GROUPS. Godzilla land seed selection also falls through to standard in this mapping.

Impact: visible actions fail, or initialize the wrong family. Repair: support the advertised groups or restrict choices honestly while completing the model. Test every exposed seed through conversion/editor/save.

## B6 — Medium: production smoke assertion contradicts requested static placeholders

Evidence: tests/test_website.py:270 demands at least three different image hashes. Actual static smoke failed at this assertion in 23.30 seconds, with one shared card-back hash. User explicitly requested that all picker samples use the card back for now.

Impact: the smoke gate stops before render/review/export/reload checks. Repair the test to check static sources, immediate selection, and zero render requests; retain downstream smoke coverage. Application placeholder behavior should remain.

## B7 — Medium: full requested reusable-template model is incomplete

Evidence: foundry/template_model.py permits ordinary groups only, native geometry and numeric offsets; it does not implement the requested formula/variant/structural-family model. Current preview approval demonstrates an image, not comprehensive validation across claimed cases.

Impact: completed-looking UI exceeds actual reusable layout support. Repair incrementally with explicit family compatibility, representative stress cards, version migration, and validated geometry. This is a feature gap, not a reason to replace Card Conjurer.
