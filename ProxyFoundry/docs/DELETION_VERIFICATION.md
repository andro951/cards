# Deck deletion and saved orders — 2026-10-01

## Behavior

- Saved orders referencing the deck ID block deletion before confirmation; the storage transaction checks again to catch a new order created after the initial check.
- Show print orders opens `#orders/<deck-id>`. Combined orders are included if any member matches. Show all print orders clears the filter; Review opens the existing saved preview; Delete print order removes the saved snapshot and schedules its ZIP cleanup.
- Confirming an unblocked deletion immediately hides the deck and shows the cached Deck Library. A workspace-scoped local journal persists the pending request. Failure restores the tile; reload resends the idempotent request.
- A metadata transaction removes the deck/render index and records its cleanup queue together. Four tasks run per worker turn, yielding between batches. Reload resumes the queue; failed cleanup retains it and offers Retry cleanup. Assets still referenced by other documents, renders, or network caches are preserved.
- Active image generation blocks UI deletion. Late render uploads targeting an already deleted deck are rejected.

## Verification

- All 511 routine tests passed in 189.15 seconds; six new deletion tests cover order ownership/races, metadata-only deletion, interrupted cleanup/retry, shared assets, revisions/idempotency, bounded cleanup batches, and late render rejection.
- All ten affected browser storage tests passed across the initial run and focused reruns. The new actual static Chromium test deliberately delays the delete response, injects a deletion failure, opens/clears the order filter, reviews/deletes a blocking order, and resumes a pending deletion after reload.
- Fixed an existing binary-storage test probe that still targeted the old response decoding statement. The assertion now inspects the current bridge and passes, including ZIP persistence after reload.
- Visually inspected the immediate library update and filtered orders page. Existing orange styling, logo, and navigation icons are retained.
- Six Node adapter/helper tests, browser JavaScript syntax checks, and all four approved vendor files passed. The production distribution was rebuilt. CI now includes the deletion browser regression in its focused gate.

The unrelated long 100-image render and extended native-frame sweeps were not rerun for this deletion change. Their earlier evidence remains in BROWSER_REPAIR_VERIFICATION.md; per-test durations remain in test-timings.csv.