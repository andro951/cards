# Browser repair verification — 2026-10-01

## Scope

The user authorized browser-only repairs, no deck image generation before Generate Images, and regression tests during implementation. The static website was exercised in actual headless Chromium. Existing orange styling and branding were preserved. No hosted application server or function was added.

## Completed checks

| Gate | Result |
|---|---|
| Routine unit/API suite | 503 passed, no failures or skips in selected group; 188.42 seconds |
| Node deck adapter/helper tests | 6 passed |
| Browser JavaScript syntax | Passed |
| Pinned Card Tools verifier | 4 canonical Git blobs match |
| Static production workflow | Normal and Custom setup → explicit generation → review → paired ZIP → reload passed; repository path `/cards/` also passed |
| Static template validation | No generation on opening; explicit two-group native preview and schema-v3 save passed |
| Source/frame choices | Static shared card backs, immediate selection, no preparation/render request before Generate passed |
| Browser storage | 7 passed: folder reconnection, competing tabs, 100 MiB files/ZIP reload, mid-job durable recovery, quota/retry, rename/log rotation, metadata caching |
| Job controls | Actual browser progress and checkpoint cancellation/reload passed |
| Mixed versions/diagnostics | Clear boot failure and downloadable diagnostics passed; image responses released |
| Affected native frames | 9 passed, including Station lands, blue Harmonized Trio Prepare, Godzilla noncreatures and black/colorless nickname tokens |
| GitHub CI | Source commit `b58109f` passed [run 36829395596](https://github.com/andro951/cards/actions/runs/36829395596), including Linux routine and actual static browser production gates |

## Long-session stress check

The final outcome is recorded after the isolated 100-image run finishes. Failed exploratory stress runs are not counted as passed verification. This uses the user's public linked Scryfall Test deck. It currently resolves four cards; the isolated test expands those actual printings into 100 distinct faces with different nickname overrides, forcing 100 uncached native outputs. The expansion exists only in the test copy, not the shipped website. This proves long-session rendering/storage behavior, rather than coverage of 100 different card families.

The current run uses an isolated regular Chromium profile with direct storage, repaired rename handling, metadata caching, quota guidance and JSON decoded to Unicode in Python before crossing either message channel. Two preceding regular-profile runs preserved 94 images and then failed reading deck metadata. Strict JavaScript UTF-8 decoding located the latest failure before message delivery, after binary conversion. Reloading read the saved metadata correctly. The revised path avoids binary conversion for JSON entirely. A recovery check using the failed profile completed the remaining six images and verified all 100 after reload; the fresh 100-image run is still pending.

The large-response regression passes with Unicode JSON, forced heap growth, GET/POST checkpoints, and malformed-payload reporting. The heap-growth probe did not reproduce corruption; [the runtime documentation](https://pyodide.org/en/stable/usage/type-conversions.html#using-python-buffer-objects-from-javascript) confirms that `toJs()` copies buffers. The underlying conversion defect is not conclusively attributed, and this is not reported as a proven WASM aliasing defect.

A preceding private-context run reached 74 saved images before its 2 GiB quota stopped it. A direct comparison measured 2 GiB for that private context versus 10 GiB for a regular profile on this machine. Available browser quotas vary; those measurements are test evidence, not promised capacities.

## Visual inspection

Inspected static frame picker, template editor with region outlines, Station-land output, blue Prepare output, and Godzilla creature output. Square fixture symbols and solid-color fixture artwork in native checks are intentional test inputs. Godzilla P/T remains above the frame; Station thresholds use the standard Station structure. The full-deck grid is inspected after completion.

## Practical limits and exclusions

The previous user's late-session crash was not conclusively attributed by the supplied logs. A real browser filesystem rename failure was reproduced independently before the fix and passes after it; the long-session result is separate evidence.

This was a routine-plus-affected repair pass. Unrelated full-sweep/merchant/multi-gigabyte cases were not routinely rerun. Historical per-test measurements remain in `test-timings.csv`. No production website was deployed. Browser-origin storage, disk quota, selected-folder permissions, and checkpoint-based cancellation remain practical constraints.

## Local artifacts

Ignored `test-results` contains JUnit reports, diagnostics, and visual evidence. Key reports: `routine-final.xml`, `production-final.xml`, `final-workflow-browser.xml`, `storage-final.xml`, `affected-native-final.xml`, `version-memory-final.xml`, and `full-deck-browser.xml`.