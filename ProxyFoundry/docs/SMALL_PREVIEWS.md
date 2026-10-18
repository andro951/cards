# Small previews and order filtering

The remaining library cover/back and order-review grids now request existing
420-pixel previews, with lazy loading and asynchronous decoding. Full-size
review/enlargement and downloaded originals are preserved.

A production API fixture using a native 2010 x 2814 Supernatural PNG measured:

| Image | Bytes | Dimensions |
| --- | ---: | --- |
| Original | 7,042,974 | 2010 x 2814 |
| Preview | 431,126 | 420 x 588 |

That fixture uses 93.9 percent fewer encoded bytes and 95.6 percent fewer pixels
for a small tile. Cold preview creation took 0.284 seconds; two cached reads took
0.0034–0.0038 seconds. These are standalone backend timings, excluding browser
transport/decoding. Original API bytes remained identical. No deck-generation
throughput improvement is inferred from these measurements.

Browser order search now hides existing tiles. In balanced before/after trials
on 400 cards, 40 input changes averaged 0.183 seconds before and 0.017 seconds
after, with child-list mutations falling from 8,240 to zero. Image element
identity, input focus and caret are retained. This isolated DOM fixture excludes
initial mounting, network, decoding and native rendering. It does not establish
large initial-grid memory or load performance.

Raw measurements: [order-previews-profile.json](order-previews-profile.json).
Reproduce with `scripts/profile_order_previews.py --image PATH_TO_NATIVE_PNG`.

Verification: 580 routine tests passed in 209.24 seconds; 16 affected component
checks passed in 28.07 seconds; five browser cases passed in 185.06 seconds.
The three complete static import/render/review/ZIP flows verify thumbnail decode,
full-size enlargement and preserved package bytes. Their rendered review page
was visually inspected. Extended component harnesses now include the actual
WorkCoordinator dependency rather than failing on unresolved module imports.