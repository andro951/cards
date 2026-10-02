# Recheck and continuation log

## Chunk 1 — baseline and preparation scheduling

Baseline main: 893adad. Started 01:31 Eastern. Real static Pyodide browser
fixture: /api/decks mean 2.503 seconds during a two-second whole job; cancellation
acknowledgment 1.7–2.9 ms. The separate cancellation control plane already works.

Resumable fixture: menu request mean 0.114 seconds (95.5% less waiting for this
fixture), cancellation acknowledgment 1.7–3.8 ms. Each artificial chunk is 100 ms;
these numbers describe scheduling, not actual deck-generation throughput.

Implemented resumable BrowserJobs, worker timer turns, and preparation generators
with saved-card yields. Local synchronous prepare drains the same steps. Added
generator result/fairness/cancel/failure tests and actual preparation saved-state,
intervening revision conflict and cancellation-after-last-card tests.

Verification: 542 routine cases passed in 197.75 seconds; all 12 focused job and
preparation cases passed in 11.69 seconds, including the four further routine
cases added during that run. All 546 current routine cases are covered. The real
static scheduling and cancellation/reload checks passed in 48.15 seconds.
JavaScript syntax, Python compilation and the four canonical vendor hashes pass.
All three real static import/setup/generate/review/paired-ZIP/reload flows passed
in 192.24 seconds, including the GitHub Pages /cards/ path. They confirm setup
does not generate, production preparation completes and output/export survives
reload. No native rendering or artwork-placement code changed in this chunk.
The chunk is ready to commit and push main.
Next: scoped UI/job ownership, route safety and additional long-job families.
