# Recommended sequence — proposals, not implementation authorization

## 1. Restore a useful production test gate

Update the stale picker test to verify static images, no generation, and immediate selection. Continue the actual static-app import -> setup -> generate -> review -> export -> reload smoke. Make this a focused routine gate; preserve long affected/full-sweep tests separately. Add browser-engine tests rather than only local-server UI tests.

## 2. Fix responsiveness and recovery first

Return job IDs immediately, run work incrementally, emit real progress, allow cancellation between units, and keep diagnostics/control requests responsive. Persist checkpoints and previous-session errors. Reproduce the user's real deck with current data and measure memory; interruption/reload must preserve completed work and give an actionable error.

## 3. Establish reliable storage ownership

Explicitly reconnect chosen folders, prevent silent workspace changes, and enforce one writer per workspace across tabs. Test permission changes and competing tabs. Prototype direct binary storage and bounded compiler scratch storage before committing to a broad migration. Preserve existing data and provide migration/backup verification.

## 4. Reduce unnecessary rendering

Keep last render separately from dirty state. Invalidate only affected faces; actual pipeline upgrades carry an explicit reason and scope. Test single-face edit, art import, symbol/back changes, new card, and mixed-deck generation. Keep picker images static.

## 5. Complete workflow and template gaps

Add the Outside-the-game opt-out. Resolve Normal Look versus default presets and the automatic-generation exception. Fix seed compatibility and then complete the promised versioned template model in supported family increments, with stress-card validation. Avoid exposing unsupported actions during that work.

## 6. Verify deployment and broaden supported sites carefully

Test GitHub Pages repository-path hosting or the chosen root domain; package/version the static build consistently. Keep the no-server rule. Add only demonstrated direct/helper import adapters, with transparent export-file alternatives.

## What I would not roll back

Keep current aesthetics, separate Choose Look, static picker samples, credits, review improvements, token choices, filename matching, presets/backups and pinned vendor strategy. Use 11b4975 as a behavioral reference for jobs/cache/reliability, not as a blanket product rollback.
