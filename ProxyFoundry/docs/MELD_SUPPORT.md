# Meld cards

Bulk Proxy Forge treats a Scryfall `layout: meld` card as one physical proxy front plus an automatic meld back.

- The meld-part front is generated through the normal Card Tools / CardConjurer renderer using its real card type.
- Scryfall's related `meld_result` image is downloaded and stored as the automatic back for that proxy.
- The automatic meld back is used by grid hover and print-order pairing.
- An explicit per-card back override still takes priority.
- The meld result is not rebuilt through an ordinary creature or planeswalker template; this avoids substituting an incorrect frame for oversized meld results.
