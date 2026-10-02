# Acceptance checks

- [x] Approved persistent filesystem browser remains alive at initial preflight.
- [x] Baseline separates main-thread responsiveness from engine queue latency.
- [x] Preparation yields only at saved-card boundaries; stale edits reject writes.
- [x] Unrelated import/setup/navigation/deletion works during generation.
- [x] Conflicts identify the affected deck/job and cannot overwrite newer edits.
- [x] No rendering or bulk artwork download in setup/frame selection.
- [x] Collection search/caret/selection and inspector drafts survive image progress.
- [x] Continuous generation progress and durable completion notification.
- [x] Bounded render/save overlap measured with byte integrity/recovery.
- [x] Pipeline experiments measured; only demonstrated benefits shipped.
- [x] Startup/UI improvements measured and version-safe.
- [x] Long-session, cancellation, reload and storage failure checks pass.
- [ ] Final checkpoint tested, committed and pushed to main with report.

Morning verification: all 699 current pytest IDs have passing results across
the all-enabled sweep and affected reruns, with no skips. See the final section
of `09_recheck_log.md`. Foreground delays during cold native startup remain an
open priority investigation, so overall goal completion is not yet established.

## Evidence by requirement

| Requirement | Authoritative evidence / scope |
| --- | --- |
| Foreground requests between background chunks | `test_static_engine_foreground_requests_between_job_chunks`; three actual worker trials below 0.75s, synthetic 100ms chunks. `test_static_metadata_import_services_foreground_reads_before_completion` verifies imports are resumable. |
| Scoped conflicts, queue ownership and cancellation | All four `test_work_coordinator.py` cases; `test_static_foreground_work_during_real_generation_preserves_setup_and_cancel_owner` checks another deck's unsaved setup, queued cancellation, foreground cancel ownership and library-started generation. |
| User choices precede generation | `test_static_cardconjurer_source_choices_are_immediate_without_generation`, frame-picker component assertions, deferred-art GitHub setup tests and production `frame-picker.js`/`github_setup.py`. |
| Continuous progress and non-disruptive completion | Production `renderDecks` sequences preparation, runtime, drawing and saving under one owner. The real native roundtrip passes after dismissing the intentional ready popup; 400-image run checks progress, completion toast, focus/caret and ready state after reload. |
| Print quality and persisted image integrity | Five downloaded Supernatural reviews and original-source pixel checks; all 132 structural task-yield PNGs exact; 196 pipeline PNGs exact RGBA/saved bytes across browser and selected-folder storage, with reload. |
| Concurrency / background-thread investigation | Measured one/two/three native renderers and actual worker compatibility; production remains one renderer because extra iframes were slower. `RENDERER_CONCURRENCY.md` records the DOM limitation and experiment scope. |
| Startup and safe bundle versions | 24 initial/warm root/subpath launches; `test_static_startup_timings_and_root_subpath_reloads`; production staged/total diagnostics; mixed website/engine version regression. One earlier isolated timeout remains unexplained, so no universal startup reliability claim is made. |
| Collection responsiveness and preview bytes | `COLLECTION_RESPONSIVENESS.md` and `SMALL_PREVIEWS.md`; stable cards/library/order filters, focus and image elements; thumbnails preserve original downloadable/print PNGs. 400-image grid visually inspected. |
| Persistence, interruption and storage failures | `test_browser_storage.py` includes quota/retry, mid-job reload, exclusive writer, failed rename, checkpoint rollback and binary archive integrity. Browser journal migration/rollback and actual 4,000-read heap regression pass. Final full-sweep result pending. |
| Long-session import/navigation acceptance | First corrected 400-output run passes save/reload/steady heap; strengthened actual-import run remains active. Four repeated printings, not 400 distinct artworks. Long menu waits remain explicitly scoped in the risk log. |
| Final sweep and handoff | All-enabled pytest process still live. The two corrected native/full-art harness cases pass; all 15 Node cases and four approved vendor hashes pass. Final totals, timings refresh and strengthened stress result remain pending. |

Detailed measurements, source maps and limitations are in `09_recheck_log.md`
and the linked `docs` reports. An unchecked gate remains incomplete.