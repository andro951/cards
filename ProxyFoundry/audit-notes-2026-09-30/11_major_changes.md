# Major changes from the working local baseline

| Change | Before, principally 11b4975 | Current e237b64 | Assessment |
|---|---|---|---|
| Execution | Installed Python app and local HTTP server | Pyodide worker and service-worker compatibility bridge | Required static goal; largest source of new operational risk |
| Jobs | Thread pool returns ID immediately | Browser operation completes before ID returns | Confirmed regression in progress/cancellation/control responsiveness |
| Storage | Ordinary disk files and SQLite | Entire workspace synchronized through MEMFS to OPFS/folder | New memory/synchronization scale risk |
| Startup | Local backend startup | Python/runtime dependencies and workspace mount before UI | More expensive cold start; consider lazy compiler startup |
| Imports | Existing Scryfall/local inputs | Primary link UI, deferred Choose Look, helper site adapters | Useful redesign; missing Outside opt-out and preset ambiguity |
| Templates | Existing frame recipes/custom source files | Browser reusable-template editor plus legacy renderer | Valuable direction; promised dynamic/structural model only partial |
| Frame picker | Generated example cards | Static shared card-back images | Latest explicit requirement, not a regression to reverse |
| Card support | Earlier Godzilla/normal recipes | Prepare, Station, helper/art-series fixes; token families; PT correction | Needed improvements; edge cases repeatedly exposed limited production coverage |
| Setup/art | Existing deck setup and metadata | Independent art/printing, credits, filename matching, presets | Keep; dirty/cache semantics still cause excess work |
| Review/export | Earlier review and local file operations | Full-page/lightbox review, warning acknowledgements, paired exports/browser downloads | Keep; production paths need reliable jobs/storage |
| Workspace recovery | Local durable job/file behavior | Browser-specific ownership, permission and worker lifecycle | New weak points needing explicit recovery |
| Quality gate | Local backend/browser/native tests | More tests, but many still use local server; static smoke stale | Test quantity exceeds actual browser operational coverage |
| Hosting | Local application | Root-oriented static dist, no server | Meets direction; repository Pages base path still unfinished |

Important milestones: 34518ca browser engine; e191b3b storage/templates/backups; 855aef6 review/art/print; 8edc446 server gateway removed; 6f7d124/96b4ca3 Choose Look; 89c846e deferred import; 2658f48 pinned vendor adapters; 7260f9e token families; 8a76d0f filename matching; 0f6eb65 static picker; 66201bf Godzilla PT; e237b64 response memory/diagnostics.

The app's useful requested features should stay. The priority is to recover the old operational qualities—responsive jobs, durable storage, bounded work and reliable cache reuse—inside the static website constraint.
