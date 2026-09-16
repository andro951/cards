# Meld cards

Bulk Proxy Forge treats a Scryfall `layout: meld` card as one physical proxy front plus its matching physical meld back.

- The meld-part front is generated through the normal Card Tools / CardConjurer renderer using its real card type.
- Scryfall's related combined `meld_result` image is downloaded automatically.
- The combined result is split into its top or bottom half based on the meld-part Oracle text, then rotated into normal card-back orientation.
- The card containing the `meld them into` instruction receives the top half; its partner receives the bottom half.
- The resulting back is used by grid hover and print-order pairing.
- An explicit per-card back override still takes priority.
- The combined meld result is not rebuilt through an ordinary creature or planeswalker template, avoiding an incorrect substitute frame for oversized meld results.
