# Engine request priority

The engine previously appended every request to a Promise chain. A synchronous
Python read finished in a microtask before another worker message could arrive,
so foreground calls effectively waited behind a burst of native asset reads.

The worker now waits for a task turn between operations, then selects pending
UI requests and foreground Python job chunks before thumbnails, native renderer
work and diagnostics/cleanup. Job chunk priority is evaluated when the queue
selects work, so a newly started import promotes an already queued chunk.
Equal priorities keep arrival order. Python operations and their durable saves
remain serialized; an active synchronous operation cannot be interrupted.
No drawing, PNG encoding or persistence format changed.

## Controlled actual-worker measurement

Three browser-storage trials submit twenty 50 ms Python asset reads, then a
Templates API request. The pre-change queue took 0.985–0.988 seconds to answer.
The final production priority queue took 0.010–0.035 seconds. Foreground job
completion in the same asset burst took 0.102–0.234 seconds. All twenty asset reads
completed in every trial. This isolates message scheduling, not public-network
throughput, whole-page latency or CardConjurer drawing speed.

Raw evidence: [baseline](request-priority-baseline.json),
[production queue](request-priority-profile.json). Reproduce the production check:

```
.venv/Scripts/python.exe scripts/profile_request_priority.py --verify
```

Five Node regressions verify foreground precedence without overlap, FIFO order,
recovery after rejection, admission across task turns, dynamic job promotion
and resource priorities.
The actual static website regression exercises the service worker and Pyodide
worker together. Broader generation, reload and storage regressions are required
because every engine request now uses this queue.

## Limits

This improves requests waiting behind pending background operations. An active
Python network read or synchronous native canvas task still runs to its next
safe boundary. Continuous foreground traffic can delay background work; its
priority is intentional. Existing native stage yields and resumable preparation
jobs provide the other scheduling boundaries. No claim of universally instant
navigation or faster PNG drawing is made.

## Actual generation flow and verification

The final actual 100-output run imports another deck during generation, verifies
its faces remain uncompiled, retains search/focus, saves all outputs without
errors/warnings and reloads ready. Settings opens in 0.41s, Templates in 1.04s,
library in 0.89s, import dialog in 0.09s, metadata import in 2.23s and return to
cards in 0.57s. The prior checkpoint measured Templates at 9.22s and metadata
import at 13.87s. These are observed separate runs with variable cache/network
conditions, not a controlled claim about whole-deck generation speed.
[Final flow evidence](request-priority-deck-profile.json).

All 23 actual website cases are covered with passing results, including the
high-address heap boundary case. Two profiler tests initially failed on missing
project import paths; both pass after correction. Seventeen storage cases pass,
and native readiness plus five full-art review/source-coordinate checks pass.
The review PNGs were visually inspected again. All 20 Node cases pass.
