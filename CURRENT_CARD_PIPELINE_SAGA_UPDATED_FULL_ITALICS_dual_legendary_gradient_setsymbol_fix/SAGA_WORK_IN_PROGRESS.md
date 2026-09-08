# Saga work in progress

These are the Saga decisions approved so far. They are now recorded in `card_data_to_cardconjurer.py`. The compiler now builds Sagas automatically, but only the known reference layout families are considered checked; unmatched Saga layouts are emitted and flagged for manual review in a sidecar report.

## Geometry approved so far

- Canvas: 2010 x 2814.
- Standard horizontal title/type/footer geometry: identical to a normal card.
- Set symbol X: **1737 px**.
- Set symbol Y: **2400 px**.
- Saga art bounds: **X 1005 px, Y 316 px, width 854 px, height 2041 px**.
- Preferred new Saga art size: **854 x 2041 px** (exact art-well size, so no crop is needed).

## Art fitting

Do not hardcode a single art X/Y/scale preset. Use Card Conjurer's cover/center-crop equation from the actual image dimensions.

If the source image is proportionally wider than the Saga art window:

```text
scale = saga_art_height / image_height
y = saga_art_y
x = saga_art_x - ((image_width * scale - saga_art_width) / 2)
```

If the source image is proportionally narrower than the Saga art window:

```text
scale = saga_art_width / image_width
x = saga_art_x
y = saga_art_y - ((image_height * scale - saga_art_height) / 2)
```

Card Conjurer displays scale as a percent. Its normal one-decimal rounding should be used before calculating the centered offset, matching the existing compiler `auto_fit()` behavior.

The portrait-land-art test produced **X 752, Y 316, scale 132.9%**. Those values are an example result, not a universal hardcoded preset.

## Checked vs. unchecked layouts

The compiler treats the six manually approved reference Sagas as the checked layout families. In practice that means chapter-group signatures of:

- `[3]`
- `[1,1,1]`
- `[3,1]`
- `[2,1]`

If a future Saga uses a different chapter-group layout, the compiler should still emit the card, but it writes that card to a sidecar JSON report named like `*_FLAGGED_UNCHECKED_SAGAS.json` so it can be reviewed manually.

## Still open

The Saga pipeline is now usable, but any new layout family beyond the reference set still needs review and approval.
