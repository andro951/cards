# Browser performance system map

## Required workflow

Gather the deck source and look, import necessary card metadata, then gather
all Art & Setup choices. No card rendering or bulk artwork retrieval belongs
in frame selection. Only Generate Images starts preparation and native output.
The user should remain able to navigate and operate on unrelated decks while
generation proceeds. Conflicting operations need scoped coordination and must
not overwrite newer edits. Completion means outputs are durably saved.

## Execution surfaces

The static website uses a service worker to route workspace API requests to
the owning browser tab. bootstrap.js forwards them to a Pyodide engine worker.
Python reuses the workspace, compiler, sources, orders and backup APIs. There
is no production HTTP server. A browser lock prevents multiple writer tabs.

Job status and cancellation have a separate control plane in bootstrap.js.
This already responds while Python is busy. Ordinary workspace reads and
mutations require the engine, whose requests share one serialized queue.
Python network calls use synchronous XHR inside that worker. Browser-owned
filesystem operations use a separate bridge and storage handlers.

CardConjurer runs in a sandboxed iframe with DOM and canvas dependencies.
The iframe shares the browser main thread. Creating more iframes does not
establish parallel CPU rendering. Its native drawing, readiness, PNG export
and saved render keys must retain print quality and output integrity.

## Storage and preparation

The selected folder or browser-managed storage holds binary files. SQLite
metadata is copied to a durable snapshot after mutations. BrowserStore skips
unchanged checkpoints and provides rollback for batched render saves. Prior
outputs survive replacement until new metadata becomes durable. Frame-cache
assets are batched during explicit generation. Renderer Blob URLs have bounded
lifetimes and are revoked on cancellation/disposal.

Preparation resolves metadata, flavor, artwork, symbols and semantic compilation
for each card. It saves each finished card using an optimistic deck revision.
Those saved-card boundaries are suitable yield points: no open SQLite transaction
or render-save batch needs to span the yield. An intervening same-deck edit
must fail the stale preparation write rather than discard the user's edit.

## Current scheduling repair

BrowserJobs accepts ordinary operations and resumable Python generators.
The worker asks for one chunk per event-loop turn. Foreground requests received
between chunks join the serialized queue before the next scheduled chunk.
Preparation yields after sources are indexed and after each persisted card.
The legacy local application drains the same generator synchronously.

Other job families remain synchronous until their own safe boundaries are
converted. A slow network request or single card preparation still blocks the
engine within that chunk. Removing global UI busy guards must therefore be
paired with scoped job/resource ownership and stale-result checks.

## User-visible progress

The shared activity panel currently represents one operation. Concurrent jobs
can replace its title/cancel handler. state.busy is a boolean used across render,
imports, GitHub setup, order generation and deletion; nested jobs save/restore
it. These are coordination weaknesses to fix before enabling concurrent UI work.
Route changes must never apply an old async response to the newly selected page.
