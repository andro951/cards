# Repair reconciliation after the audit

Updated 2026-10-01. The preceding audit files describe main at `e237b64` and remain historical evidence. The user subsequently authorized browser-only repairs and tests, with no deck generation before Generate Images.

| Audit area | Implemented repair | Evidence |
|---|---|---|
| Production test gate | Static placeholder selection and actual website import → setup → generate → review → export → reload; routine CI plus focused static browser gate | `tests/test_website.py`, workflow CI |
| Browser job responsiveness | Immediate IDs, queued execution, progress/cancel channels independent of worker operation, bounded job history | Browser job and static Chromium cancellation tests |
| Recovery and diagnostics | Durable metadata snapshots, per-card preparation checkpoints, saved completed PNGs, previous-session browser diagnostics | Mid-generation reload and quota/retry tests |
| Storage ownership | Direct binary file storage, explicit folder reconnection, one writer tab, service-worker owner recovery | Nine actual browser storage tests |
| Large-session filesystem bug | Flush pending writers before reads/rename; update Emscripten node parent/name after rename; clean failed writers | Before-fix rename probe failed; committed regression checks pass, including log rotation |
| High-memory browser transport | Avoid signed Pyodide byte/ASCII offsets above 2 GiB using marked Unicode replies/events, Base64 inline binary and direct file input; unsigned filesystem offsets | Reproduced corrupted bytes and signed-offset exception; high-address binary/upload/file/ASCII/job regression passes |
| Failed-upload recovery | Remove newly created rename destination after failure, preserve existing destination, repair incomplete hashed asset on retry | Browser quota failure reproduced before fix; both destination cases and unit retry checks pass |
| Unnecessary rendering | Preserve stale previous images; draft compilation is not a pipeline upgrade; render only changed keys; grid uses bounded thumbnails | Cache/invalidation API tests and static workflow |
| Normal/Custom workflow | Both gather input before Generate Images; Normal ignores custom global frame/art defaults | Dirty-default static website test |
| Outside-the-game control | Default inclusion with explicit opt-out in import/add-card UI | Workflow and deck importer tests |
| Dynamic templates | Schema v3 migration, all native text slots, checked formulas, conditional variants, required-slot validation, portable assets, explicit multi-group preview approval | Template v3/backup tests and actual browser editor test |
| GitHub Pages | Root or repository-path build, build version checks, manual publish workflow | Actual `/cards/` workflow and mixed-version failure test |
| Test grouping | Fast routine gate, affected extended runs, optional full sweep; measured per-test CSV | `docs/TESTING.md`, `scripts/test_policy.py`, CI |

## Preserved product decisions

The orange visual style, actual branding, separate Choose Look, static frame samples, art credits, review/export improvements, token choices, filename matching, presets/backups, permanent deletion, fallback-off default and pinned vendor strategy remain. The old launcher remains available.

## Remaining practical limits

Cancellation takes effect between work units; an active native image render is not preempted mid-canvas. A browser-origin workspace has one writer; browser profiles and hosting origins have separate storage. Browser-managed quota and disk space remain finite. Folder access depends on browser support and permissions. Cross-origin deck hosts still need an approved helper or exported deck file. Template family claims must contain actual compatible structure; selecting a group cannot manufacture unsupported renderer slots.

The historical 80/100 failure is not conclusively attributed to the supplied logs. The discovered rename bug is independently reproduced and repaired. The final verification report records the separate 100-image run and precisely describes its test data.