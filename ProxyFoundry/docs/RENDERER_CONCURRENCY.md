# Native renderer concurrency

Production remains at one renderer. Two native iframes did not improve measured
throughput, and three worsened it. Each also duplicates large native canvas
surfaces and decoded assets. The experiment changes only a temporary static
build; it does not introduce parallel production saves or generation before
the explicit Generate Images action.

## Balanced warm comparison

Seven structural faces use Supernatural artwork at the production 2010×2814
output resolution. Every iframe is primed with every face before measurement,
so distributing cards across different frame caches does not bias the result.
Two repetitions run in the order 1, 2, 3, 3, 2, 1. Startup, priming, plan reads,
PNG result collection and filesystem saves are excluded. This measures native
rendering, not whole-deck throughput.

| Renderers | Mean seven-face time | Mean longest reported task | Canvas pixel-surface estimate |
| --- | ---: | ---: | ---: |
| 1 | 6.099 s | 330 ms | 334 MB |
| 2 | 6.241 s | 361 ms | 669 MB |
| 3 | 7.099 s | 384 ms | 1,003 MB |

Two renderers were 2.3 percent slower and three 16.4 percent slower. Timer gaps
remain near one second, so this does not solve that remaining responsiveness
finding. A prior balanced run also showed no gain (6.239/6.369/7.047 seconds).

The surface estimate sums distinct DOM and global detached canvases at four
bytes per pixel. It is not measured process RAM or GPU allocation: browser
allocation can be lazy, and decoded images, compressed caches, double buffering
and other allocations are excluded. JS heap is recorded separately and does not
represent native canvas memory. Reported long tasks describe main-thread busy
periods, not total process CPU utilization.

All 42 measured PNGs match the single-renderer reference across every RGBA
channel. The regression passed in 400.02 seconds. Priming renders are not counted
as measured outputs. The canonical vendor hashes remain unchanged.

## Worker compatibility

The DOM-only findings below are historical. The subsequent dedicated-worker
adapter and full-deck measurement are documented in [NATIVE_RENDER_WORKERS.md](NATIVE_RENDER_WORKERS.md).

An actual dedicated worker was given the pinned production creator script.
OffscreenCanvas is available, but the script fails during initialization with
`ReferenceError: window is not defined`; the worker has neither window nor
document. The production adapter also uses DOM controls, native image/font
readiness and the core's canvas globals. This establishes that the current core
cannot simply be moved unchanged into a worker. It does not establish that an
adapted renderer or isolated worker encoding could never work.

Keep the measured stage yields and one native renderer. Further worker work
should isolate a proven expensive stage, preserve exact pixels, and account for
transfer/copy/memory costs before changing production.

Reproduce with `scripts/profile_renderer_concurrency.py` or
`tests/test_native_concurrency.py` using `PF_BROWSER=1` and `PF_LIVE_CC=1`.
Windows measurements use visible Chromium. Raw evidence is in
[renderer-concurrency-profile.json](renderer-concurrency-profile.json).