# Source map and interactions

| System | Principal source | Interaction |
|---|---|---|
| Website boot | web/bootstrap.js, scripts/build_web.py | Starts worker, establishes bridge, loads UI |
| Browser engine | web/engine-worker.js, foundry/browser.py | Serialized API dispatch into Python; POST filesystem synchronization |
| Workspace selection | web/storage-choice.js | IndexedDB preference, folder permission, OPFS fallback |
| HTTP compatibility | web service worker and bridge modules | UI/runtime requests routed to owning worker |
| Domain/workspace | foundry/workspace.py, domain.py, storage.py | Deck mutations, preparation, caches, binary files, database |
| Original jobs | foundry/jobs.py | ThreadPoolExecutor with early ID and live progress |
| Browser jobs | foundry/browser.py:31 | Inline operation, ID returned after completion |
| Library/import/look | site/deck.js | Import, hardcoded Outside inclusion, Normal Look auto-render |
| Setup/picker | site/setup.js | Art and frame choices, now static picker images |
| Rendering | site/render.js, foundry/compiler.py | Compile plans, native renderer, results/cache |
| Reusable templates | web/templates-browser.js, foundry/template_model.py | Version 2 ordinary-group conversion/editor |
| Review/export | site/deck.js, site/orders.js, foundry workspace/order modules | Review images, warning acknowledgement, paired exports |
| Test gates | tests/test_website.py, tests/test_browser.py, .github/workflows/proxy-foundry-ci.yml | Static production smoke versus local-server browser fixtures |

Browser flow: UI -> service-worker/bridge -> serialized engine-worker -> Python workspace -> synchronized MEMFS -> OPFS/folder. Card rendering also uses the native Card Conjurer runtime. Busy Python work can hold later API requests even though the outer page remains responsive.

Inventory.csv records scoped first-party Python/JavaScript sources and tests, byte sizes, line counts, and modification times. Vendor, generated dist, caches, and environments are excluded. This is a behavior-focused audit, not a line-by-line certification of every source file.
