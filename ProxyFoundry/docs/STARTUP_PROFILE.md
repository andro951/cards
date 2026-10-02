# Browser startup measurements

Twelve launches before and twelve after instrumentation completed at both `/`
and `/cards/`, including fresh contexts and warm reloads. No import or rendering
runs during this profiler. The browser process may retain CDN HTTP cache across
fresh contexts; these are not twelve completely cold machines.

Initial measured Pyodide initialization was 2.28–2.69 seconds, Pillow
0.24–0.45 seconds, workspace opening 0.02–0.03 seconds, bundle fetch/unpack
0.20–0.27 seconds and Python application import/init 1.66–1.95 seconds.
The local bundle's transfer portion subsequently measured below 0.1 seconds;
unpacking was about 0.12–0.15 seconds. This is local static transport and does
not predict public GitHub Pages network latency. These measurements do not
justify adding another cache layer or changing startup dependencies.

Production now records `startup timing` entries in browser diagnostics with
stage, seconds, storage type, engine total/outcome and the last stage reached.
Stages above 0.1 seconds are recorded; the total is always recorded. Messages
identify image-tool loading, saved workspace opening, application bundle loading
and workspace-tool initialization. The website total runs from bootstrap module
execution to UI reveal; it excludes initial HTML/module fetch and a service-worker
installation reload. The standalone profiler's navigation timer includes those
costs. Engine total starts when worker startup is invoked and excludes module
loading before that invocation. Totals are inclusive; do not add them to stages.

Seven deterministic Node cases cover successful browser/folder storage startup
and failures at engine, Pillow, bundle fetch/unpack and app initialization. The
actual static startup test checks root/subpath cold/warm launches, successful
engine totals and persisted website timing diagnostics. It passed in 56.36s.
The earlier isolated startup timeout remains unexplained: repeated successful
launches do not prove that failure has been fixed. Failure capture and the final
full sweep remain required evidence.

Raw trials: [baseline](startup-baseline.json), [instrumented](startup-stages.json).
Reproduce with `scripts/profile_startup.py`; the only test injection collects
worker timing messages and does not replace the application engine.