# Full-art canvas fitting verification

Verified 2026-10-01 using the production static browser engine and pinned CardConjurer.

## Cause and fix

Godzilla fitting used an 80-pixel inset. Native land templates supplied a shorter art window (typically 92.24% of card height), so fitting to those windows could leave unused canvas or shift the composition. Full-art treatment now sets normalized art bounds to x=0, y=0, width=1, height=1 after the frame recipe is composed.

The existing centered cover calculation is retained: scale is the larger of card-width/source-width and card-height/source-height. Each overflowing axis is offset by half its excess. Exact card-sized art therefore has zoom=1 and x=y=0. CardConjurer draws art from its top-left origin using normalized card coordinates; this was confirmed in the pinned creator script. No vendor renderer or frame code was copied or changed. Manual fit overrides and supplied raw cards are preserved. Pipeline v29 makes previous render results stale.

## Actual browser examples

| Card | Original frame family |
| --- | --- |
| Syr Gwyn / Dean Winchester | Godzilla full-art nonland |
| Orzhov Basilica / St. Mary's Convent | Original dual-color full-art land |
| Savai Triome / The Cosmic Crossroads | Original tri-color full-art land |
| Takenuma / The Veil | Original crowned legendary full-art land |
| Command Tower / Men of Letters War Room | Original five-color full-art land |

The test stages original Supernatural artwork and data.json in an isolated built website, clicks Generate Images, waits for completion, then uses Download Review Images. The original source files are copied unchanged. The downloaded reviews contain the Scryfall printing on the left and the generated custom card on the right.

All five compiled placements use full-card bounds and independently calculated centered cover offsets. Three unobscured points per generated card are compared with source pixels at full-card coordinates; the maximum channel difference was 6/255, within browser resampling tolerance. Visual inspection of all five sources and reviews confirmed matching landmarks, scale and centering, with artwork filling the canvas behind overlays. The credit strip and rounded corner clipping are part of the frame output.

## Gates

- Routine: 519 passed, no failures or skips in the selected group, 280.52 seconds.
- Affected live static browser test: 1 passed, 338.24 seconds; generates five images and downloads five reviews.
- Approved vendor blobs: unchanged.
- Tests cover Godzilla lands/nonlands, basic lands, dual/tri/legendary/five-color land recipes, wider/taller artwork, and manual placement preservation.

The 89 unrelated/conditional extended tests were not part of the routine selection; no full stress sweep was requested. Local artifacts are in ignored test-results/supernatural-full-art. Delivery contains exactly ten PNGs: five downloaded reviews and five untouched original art images.
