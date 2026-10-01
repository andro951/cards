# Browser repair verification — 2026-10-01

## Scope

The user authorized browser-only repairs, no deck image generation before Generate Images, and regression tests during implementation. The static website was exercised in actual headless Chromium. Existing orange styling and branding were preserved. No hosted application server or function was added.

## Completed checks

| Gate | Result |
|---|---|
| Routine unit/API suite | 505 passed, no failures or skips in selected group; 225.18 seconds |
| Node deck adapter/helper tests | 6 passed |
| Browser JavaScript syntax | Passed |
| Pinned Card Tools verifier | 4 canonical Git blobs match |
| Static production workflow | Normal and Custom setup → explicit generation → review → paired ZIP → reload passed; repository path `/cards/` also passed |
| Static template validation | No generation on opening; explicit two-group native preview and schema-v3 save passed |
| Source/frame choices | Static shared card backs, immediate selection, no preparation/render request before Generate passed |
| Browser storage | 9 passed in 174.11 seconds: folder reconnection, competing tabs, 100 MiB files/ZIP reload, mid-job durable recovery, quota/retry, rename/log rotation, metadata caching, failed-rename preservation and retry |
| Job controls | Actual browser progress and checkpoint cancellation/reload passed |
| Response integrity | 120 binary replies, Unicode JSON, fallback Base64 decoder, malformed payloads, released proxies and downloadable diagnostics passed |
| Search spacing | Deck/card search placeholders clear the icon; actual `/cards/` workflow passed in 66.81 seconds |
| High-address regression | Binary hash, 20 MiB upload, filesystem write/rename/read, ASCII JSON, response metadata and progress event integrity above 2 GiB passed; real Command Tower import/art/frame/render/readback at that boundary passed in 83.73 seconds |
| Affected native frames | 9 passed, including Station lands, blue Harmonized Trio Prepare, Godzilla noncreatures and black/colorless nickname tokens |
| GitHub CI | Source commit `3f2a0e1` passed [run 36844569844](https://github.com/andro951/cards/actions/runs/36844569844); the final source gate is recorded after the push |

## Long-session stress check

The final outcome is recorded after the isolated 100-image run finishes. Failed exploratory stress runs are not counted as passed verification. This uses the user's public linked Scryfall Test deck. It currently resolves four cards; the isolated test expands those actual printings into 100 distinct faces with different nickname overrides, forcing 100 uncached native outputs. The expansion exists only in the test copy, not the shipped website. This checks long-session rendering/storage behavior rather than coverage of 100 different card families.

Three preceding regular-profile runs preserved 94 images and then failed at JSON or native frame transfer. A short reproduction finally isolated the pinned runtime conversion defect: with 110 × 20 MiB allocations held, a 1 MiB high-address memoryview returned the wrong SHA-256 through `toJs()`. Its `getBuffer()` conversion raised a negative-offset RangeError. JSON-only workarounds let metadata pass but did not fix frame bytes.

The pinned [buffer converter](https://github.com/pyodide/pyodide/blob/314.0.7/src/core/python2js_buffer.js) slices the heap with signed offsets. The [ASCII converter](https://github.com/pyodide/pyodide/blob/314.0.7/src/core/python2js.c) has the same boundary issue. This is a reproduced signed-address conversion problem, not memory aliasing: [the documentation](https://pyodide.org/en/stable/usage/type-conversions.html#using-python-buffer-objects-from-javascript) says `toJs()` copies buffers.

A high-address ASCII response-header test also failed before the final metadata repair and passes afterward. The application bridge uses marked Unicode text for JSON, response metadata and job events to avoid that ASCII path and Base64 for small inline binary replies. Uploaded/network buffers use the supported [`to_file()` API](https://pyodide.org/en/stable/usage/api/python-api/ffi.html#pyodide.ffi.JsBuffer.to_file) through a temporary workspace file; filesystem offsets are unsigned. Saved PNGs and ZIPs still travel as browser file descriptors/Blobs, avoiding Base64 for large stored files. No runtime or CardConjurer vendor source was copied or patched. The current full-deck run uses the high-address binary/input/filesystem bridge and an isolated regular Chromium profile; its final result is pending. It started before the later metadata, progress-event and failed-rename refinements. The final source separately passed the forced-boundary real native render, normal workflow and nine storage checks.

A preceding private-context run reached 74 saved images before its 2 GiB quota stopped it. A direct comparison measured 2 GiB for that private context versus 10 GiB for a regular profile on this machine. Available browser quotas vary; those measurements are test evidence, not promised capacities.

Quota failure testing also reproduced a new empty destination surviving a failed rename. The repair removes a newly created destination, preserves an existing one, retains the source, and permits retry. Hashed asset retries repair incomplete files as well. These are verified separately from the full-deck run.

## Visual inspection

Inspected static frame picker, template editor with region outlines, Station-land output, blue Prepare output, Godzilla creature output, and the real Command Tower grid after forced high-address generation. Square fixture symbols and solid-color fixture artwork in native checks are intentional test inputs. Godzilla P/T remains above the frame; Station thresholds use the standard Station structure. The full-deck grid is inspected after completion.

## Practical limits and exclusions

The previous user's late-session crash was not conclusively attributed by the supplied logs. The new high-address reproduction and repeated 94-image failures supply independent evidence for a concrete bridge defect. Browser rendering still needs memory for the active compiler and image; direct storage avoids retaining the entire workspace inside Python memory.

This was a routine-plus-affected repair pass. Unrelated full-sweep/merchant/multi-gigabyte cases were not routinely rerun. Historical per-test measurements remain in `test-timings.csv`. No production website was deployed. Browser-origin storage, disk quota, selected-folder permissions, and checkpoint-based cancellation remain practical constraints.

## Local artifacts

Ignored `test-results` contains JUnit reports, diagnostics, and visual evidence. Key reports: `routine-complete-final.xml`, `production-final.xml`, `bridge-workflow-final.xml`, `storage-complete-final.xml`, `affected-native-final.xml`, `version-memory-final.xml`, `bridge-complete-final.xml`, `high-address-native-final.xml`, and `full-deck-browser-final.xml`.