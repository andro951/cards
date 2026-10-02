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

Repair pending: resource ownership, generation queue, activity ownership and
route-safe callbacks. Tests must cover simultaneous unrelated actions and
specific same-deck conflicts, duplicate clicks and late responses.

## Medium: concurrent activity ownership is undefined

Evidence: ui.job and runRenderPlan overwrite one activity cancel button;
busy restoration uses previous boolean values. Enabling concurrency without
repair would allow wrong-task cancellation and inaccurate unload protection.

Repair pending: token-based active work accounting and owned progress/cancel.
