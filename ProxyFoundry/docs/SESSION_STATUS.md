# Proxy Foundry 1.2 — integrated Card Tools v58

The v58 update is implemented and the supplied ten-file vendor package is preserved byte-for-byte. The handoff changes cover Flip medallion clearance, native Station structure/parser, calibrated native badge/P/T drawing, Station pinline colors, and landscape artwork placement. See `CARD_TOOLS_V58_UPDATE.md` for details and the additional native Station module's content pin.

## Verified runtime milestone

Executable rendering/test source: commit `92e72f3ed2eb4962e0a9ff3ae506105d1d0ff2e9` in `andro951/cards`. GitHub Actions run `35033784334` completed successfully. Its JUnit report contains 153 cases: **151 passed, 0 failed, 0 errors, 2 optional offline-only cases skipped**, in 297.871 seconds. Real HTTP/browser and native renderer tests were enabled.

The native Station smoke test renders four Station variants plus one interleaved ordinary creature. Native draw-call assertions verify full-alpha 151.2-square badges, 306 × 148 P/T assets, the saved threshold values, compact/three-region settings, and paired order backs. Tests also include the existing eleven-face native structural suite, artist-credit browser controls, safe imports, cache rules, vendor parity, and the actually installed helper transferring a multi-chunk ZIP. The merchant editor is a controlled fixture, never a live purchase.

Post-milestone changes finalize release labels, the legacy-launcher label and documentation. The full release suite is run again on the release-preparation commit; its artifact records the exact source and result. No source outside ProxyFoundry is changed by this release-preparation step.

Artist resolver/UI and printer-helper files compare byte-for-byte with Proxy Foundry 1.1. An installed integrated helper 1.0.0 does not need reinstallation. A new generation key marks earlier prepared decks for regeneration while retaining existing images and saved order snapshots.

The distribution is one extractable application ZIP, not a nested checkpoint. It excludes repository archives, renderer/font caches, private keys, browser profiles, and generated test workspaces. The Windows launchers are provided but have not been executed by Linux CI. Live merchant UI changes and manufacturing output require user acceptance checks.
