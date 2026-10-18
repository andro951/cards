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
The worker asks for one chunk per event-loop turn. RequestQueue admits new
messages across task turns, then ranks UI requests ahead of thumbnails, native
work and diagnostics/cleanup. Each operation and its durable save remains
serialized; equal priorities keep arrival order.
Preparation yields after sources are indexed and after each persisted card.
The legacy local application drains the same generator synchronously.

Imports now yield between resolved metadata rows and publish the deck only after
all rows finish. Add Cards retains its starting revision so intervening edits
reject the final write. Runtime preparation yields after each pinned dependency.
Foreground jobs preempt background preparation at these boundaries, with equal
priorities rotating and cancelled jobs closing first. Whole-deck preparation and
runtime setup are background jobs; imports remain foreground jobs.

A slow network request or single card preparation still blocks the engine within
that chunk. GitHub setup, archives, orders and backups now yield at their own
safe boundaries. Scoped ownership permits independent deck work but does not
make Python operations parallel. Native renderer concurrency and render/save
overlap remain experimental because measurements did not support shipping them.

## User-visible progress

WorkCoordinator owns active tasks, per-deck leases, exclusive workspace changes
and the single native-render queue. Foreground progress temporarily replaces
background progress, with a cancel button belonging to that task. Finishing it
restores background progress. Queued generations have separate cancel buttons.
state.busy derives from all active/queued work for unload protection.

Deck/settings/templates/orders views reject stale route responses. Generation
refreshes only its own visible cards view; completion preserves unsaved setup
and existing dialogs. Whole-workspace restore/location changes are exclusive,
and location cancellation releases their lease before another change begins.
