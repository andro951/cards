# Reusing normalized artwork

Repeated image ingestion now uses a bounded per-workspace cache keyed by all
source bytes (SHA-256) and the transparent-trimming choice. It retains at most
128 source hashes and asset IDs, with no raw bytes or decoded images. Before
reuse it checks the actual saved asset. Missing assets are normalized/restored;
changed source bytes and different trimming choices take the existing decode
and PNG encode path. The in-memory cache resets when the engine restarts.

This runs where artwork was already ingested. It adds no pre-generation downloads
or rendering. Network refresh policy and GitHub blob verification still happen
before artwork ingestion; reuse cannot hide changed remote bytes. Native final
render validation/saving is unaffected. No pipeline/cache version bump is needed
because the normalized PNG bytes remain identical.

Balanced trials in the actual static Pyodide browser engine repeated a warm
2010 x 2814, 7,042,974-byte PNG eight times per trial:

| Path | Trial seconds | Mean per ingestion |
| --- | --- | ---: |
| Existing normalization | 27.748 / 26.556 | 3.394 |
| Reuse existing normalized asset | 0.339 / 0.321 | 0.041 |

All four trials returned the same normalized PNG SHA-256, dimensions and bytes.
The operation timer excludes startup and request-body transfer. The normalization
benchmark overlapped an independent large preparation test, so absolute times
reflect that machine/load. This shows a benefit for identical warm artwork,
not an 82-fold improvement in deck throughput or new-image preparation.
First-time artwork still needs validation, decoding and encoding.

Unit checks cover byte identity, returned metadata independence, changed input,
trim separation, deleted-asset recovery, invalid input, bounded retention and
recent-input reuse. Six image cases pass in 10.06 seconds; the actual browser
normalization check and all three complete static import/render/review/ZIP flows
pass in 205.78 seconds. All 583 routine tests pass in 232.42 seconds.

Raw measurements: [image-ingest-profile.json](image-ingest-profile.json).
Reproduce: `scripts/profile_image_ingest.py --image PATH_TO_ARTWORK`.

The committed measurements used historical revision d9e78e9. Pass
`--baseline d9e78e9` to reproduce that comparison with repository history present.
The default and automated browser test temporarily disable the cache in the
isolated fixture for the normalization comparison. This avoids a dependency on
Git history in shallow CI checkouts; production behavior is not patched.
