# Collection responsiveness

Generation progress now updates existing card/deck tiles instead of remounting
the page. Search input, caret, focus, card buttons, scroll position and open
inspector controls stay in place. Filters and Select All work against the visible
collection. Library image updates no longer fetch templates. The active updater
follows navigation, and its failed read is logged without interrupting generation.
Only the current card grid has a retained updater; old deck DOM is released on
navigation. Deck completion uses one notification and preserves focused inputs.

## Isolated DOM/JavaScript comparison

Previous UI: d1888b3. Identical offline fixtures in headless Chromium: 400 cards,
300 decks, 20 progress updates and 40 search changes. Two trials per variant in
balanced order. Initial mount, network, native rendering and persistence are
excluded. This measures collection work, not whole-deck throughput.

| Operation | Previous mean | Updated mean |
| --- | ---: | ---: |
| Card progress, 20 updates | 0.682 s | 0.046 s |
| Card search, 40 changes | 0.683 s | 0.018 s |
| Library progress, 20 updates | 0.254 s | 0.145 s |
| Library search, 40 changes | 1.430 s | 0.016 s |

Previous updates replaced the page and lost search focus. Updated trials retained
the same search element, card buttons and focus, with zero main-container
remounts. Template reads during library updates fell from 20 to zero. This does
not remove CardConjurer's separately measured main-thread pauses or the full deck
snapshot still fetched for a visible card-grid progress update.

Reproduce with `scripts/profile_collection_updates.py`. Raw trials are in
[collection-update-profile.json](collection-update-profile.json).

## Verification

Offline regressions cover the large collections, no-match filters, selection,
caret, stable tiles and an inspector draft during progress. Real static native
rendering covers search retention after generation started on the deck page,
and after generation started in the library and the user opened the card grid.
An injected progress-read failure in the latter case does not stop generation.
The rendered thumbnail, final counts and success notification still appear.
The normal/custom/GitHub-Pages import, setup, generation, review, paired-ZIP and
reload flows pass. No native frame/art/drawing code changed.