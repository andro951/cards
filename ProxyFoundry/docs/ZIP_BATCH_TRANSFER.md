# Paired ZIP batch transfer

Print Helper 1.1.0 keeps the original image resolution and bytes. The whole saved order ZIP remains the download/archive; it is not replaced, recompressed, or resized. The helper reads independent ZIP views of that saved snapshot, each at most 1 GiB including headers and its directory. A front/back pair is never split. Global six-digit filenames keep every copy uniquely paired across batches.

Small orders are transferred byte-for-byte as their original ZIP. Large orders use virtual ZIP headers/directories plus range reads into the existing stored archive: no extra multi-gigabyte batch files, no full-archive JavaScript buffer, and no changes to the renderer or render cache. One batch File is assembled at a time, uploaded, checked, and released before the next. This bounds helper retention; it cannot bound the printer site's own memory usage.

Metadata protocol 2 exposes batch index/count/size/filename. The original authenticated ZIP endpoint still works for old small-order helpers. New bounded batch range requests use the same per-transfer secret and exact authorized printer tab, reject invalid indexes/ranges, and fail if the saved ZIP changes. Authorization expires after an hour of inactivity rather than one hour since the order started.

Add/Replace is asked once using the existing detection and deletion safeguards. Batches then append to the same design. After each upload, processing must finish and the cumulative count must match before another batch is sent. Any error or cancellation stops subsequent uploads. No failed batch is automatically retried: the printer may already have partially imported it. Review the existing design before retrying to avoid duplicates. Checkout is never clicked.

The review dialog closes immediately after a valid Build paired ZIP click. Packaging continues in the activity panel; errors use a toast. Shared modal header/footer radii and clipping preserve the outline on desktop and mobile.

Reload the updated unpacked helper (do not uninstall it), reload Bulk Proxy Forge, then reopen the saved order. Existing large saved archives can be batched without rerendering or rebuilding them.

Tests include byte-exact pair/copy preservation, exact archive-size boundaries, authorization/range errors, source mutation, sequential browser uploads, Add/Replace, cancellation, failure stops, and immediate dialog close. The opt-in PF_LARGE_TRANSFER=1 test exercises a real 278-card / approximately 2.3 GiB archive; PF_BROWSER=1 runs the installed-extension tests. Merchant browser tests use controlled fixtures and do not place live orders.
