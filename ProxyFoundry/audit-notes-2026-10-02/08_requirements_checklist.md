# Acceptance checks

- [x] Approved persistent filesystem browser remains alive at initial preflight.
- [x] Baseline separates main-thread responsiveness from engine queue latency.
- [x] Preparation yields only at saved-card boundaries; stale edits reject writes.
- [x] Unrelated import/setup/navigation/deletion works during generation.
- [x] Conflicts identify the affected deck/job and cannot overwrite newer edits.
- [x] No rendering or bulk artwork download in setup/frame selection.
- [x] Collection search/caret/selection and inspector drafts survive image progress.
- [ ] Continuous generation progress and durable completion notification.
- [x] Bounded render/save overlap measured with byte integrity/recovery.
- [x] Pipeline experiments measured; only demonstrated benefits shipped.
- [ ] Startup/UI improvements measured and version-safe.
- [ ] Long-session, cancellation, reload and storage failure checks pass.
- [ ] Final checkpoint tested, committed and pushed to main with report.
