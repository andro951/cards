# Source map

| System | Entry points and interactions |
| --- | --- |
| Startup/routing | web/bootstrap.js, web/service-worker.js → engine-worker.js |
| Worker scheduling | engine-worker.js sequence, scheduleJobs, scheduleCleanup |
| Python jobs | foundry/browser.py BrowserJobs.start/run_pending/_step |
| Preparation | server.App.prepare_deck_steps → Workspace.prepare_steps → _prepare_card_faces |
| Rendering | site/render.js runRenderPlan → runtime-bridge.js → native iframe → render save API |
| UI locks/progress | site/ui.js state.busy/job/activity; deck.js, github-setup.js, deletion.js, orders.js |
| Storage | BrowserStore, workspace-fs.js, workspace-files.js, storage-choice.js |
| Baseline | scripts/profile_responsiveness.py, docs/responsiveness-*.json |

Use function anchors; line numbers drift during repairs. Source inventory is
limited to this performance task, rather than repeating the entire repo audit.
