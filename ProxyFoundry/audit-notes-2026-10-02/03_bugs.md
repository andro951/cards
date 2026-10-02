# Confirmed responsiveness bugs

## High: engine reads wait behind whole jobs

Evidence: engine-worker.js appended runJobs immediately after every request;
BrowserJobs.run_pending drained operations synchronously. A real static-site
two-second fixture delayed /api/decks 2.485–2.524 seconds. Browser main-thread
timer gaps stayed below 24 ms, isolating the delay to engine scheduling.

Repair: generator chunks at durable boundaries, timer turns between chunks,
and foreground request servicing. Regression: actual service worker and Pyodide
benchmark requires foreground responses below 750 ms for 100 ms chunks.
Initial repaired fixture measured 107–118 ms. Single operations remain bounded
only by their own internal work; more families require conversion.

## High: unrelated user actions rejected by global boolean

Evidence: addNewDeck/importDeck, GitHub setup and deleteDeck reject state.busy;
runRenderPlan also rejects all work. User impact: menus/import/deletion cannot
operate on independent decks during generation.

Repaired in chunk 2: per-deck resource ownership, a cancellable native queue,
owned activity and route-safe callbacks. Actual static tests import a second
deck during a held native render, preserve its unsaved artist credit, cancel
foreground work without cancelling generation, and cancel a queued generation.
The existing deletion/order-dependency/recovery test now deletes an unrelated
deck while background work remains active. Same-deck writes identify the owner.

## Medium: concurrent activity ownership is undefined

Evidence: ui.job and runRenderPlan overwrite one activity cancel button;
busy restoration uses previous boolean values. Enabling concurrency without
repair would allow wrong-task cancellation and inaccurate unload protection.

Repaired in chunk 2: task-based active work accounting and owned progress/cancel.
Finishing foreground work restores retained generation progress. Workspace-wide
restore can cancel through its own exclusive lease. Picker cancellation releases
that lease, and conflicts are rejected before a native picker can be opened.

## High: image progress replaces active collection controls

Evidence before chunk 5: deck.generate calls showDeck after each image, replacing
main and rebuilding the grid; library generation calls refreshLibrary (including
templates) and showLibrary after each image. Search itself also reconstructs the
collection. The offline comparison against d1888b3 confirms old progress loses
search focus and node identity, and performs 20 unnecessary template reads.

Repaired in chunk 5: stable tile/status updates and filtering with existing
controls. Visible-view ownership follows navigation and releases old grids;
progress-read failure logs without stopping native generation. Completion preserves
focused inputs and emits one deck notification. Actual generation tests retain
search/caret/card buttons, including library-to-card navigation and an injected
failed progress read. Offline 400-card/300-deck cases retain inspector drafts and
selection. Full-deck snapshot reads and native drawing pauses remain separate risks.


## High: foreground requests wait behind native asset bursts

The old Promise chain begins the next synchronous Python operation before
incoming worker messages can be delivered. A controlled twenty-read asset
burst makes a Templates request wait about 0.99 seconds even though its handler
is fast. RequestQueue yields a task turn, then ranks pending UI calls and
foreground Python chunks ahead of background assets/jobs. Foreground job rank
is dynamic so a queued background chunk is promoted when an import starts.

The final controlled actual-worker trials answer in 10–35 ms and finish a
foreground job in 102–234 ms; all asset requests complete. Five Node regressions
cover precedence, serialization, task admission, rejection and job promotion.
See docs/REQUEST_PRIORITY.md. All 23 website cases have passing results, including corrected standalone profiler reruns and the high-memory boundary case.
