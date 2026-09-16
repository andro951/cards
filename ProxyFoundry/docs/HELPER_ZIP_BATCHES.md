# Full-quality, multi-ZIP print transfers

Print helper **1.1.0** sends a large saved order to the same TCGPlaytest design as sequential, independently readable ZIPs. Each batch is at most **1,073,741,824 bytes** (the existing UI's “1 GB”, or 1 GiB), including local headers, the central directory and the end record. A batch closes before adding the next whole front/back pair would cross that ceiling. Exact fits are allowed. A single pair that cannot fit fails clearly; it is never separated or downscaled.

## What stays unchanged

CardConjurer renders, resolution, PNG image bytes, backs, quantities, order snapshots and the full ZIP download are unchanged. No renderer/template version bump is needed. Global pair names such as `FRONT/000177.png` and `BACK/000177.png` are retained across batches. These are ordinary complete ZIP files, **not** split ZIP volumes.

`foundry/transfer_zip.py` builds small ZIP header/offset tables over the original saved archive. The HTTP server reads bounded ranges directly from the saved file; it never loads the full order into memory or creates another multi-gigabyte copy on disk. ZIP64 source offsets are supported. Small orders transfer their original ZIP byte-for-byte.

## Helper behavior

The helper asks Add/Replace once, before any upload or deletion. It then transfers one batch in 1 MiB messages, assembles only that batch's File, uploads it, and waits for processing and the expected cumulative card count before starting another. It releases its previous input/File references before the next transfer. The printer may retain decoded images for the completed design; this feature does not remove the printer's own memory or size constraints.

After every batch is confirmed, it opens the preview once. It never clicks checkout or pays. Cancellation, malformed/truncated ranges and failed uploads stop later batches. No failed batch is automatically retried: a printer may have partially accepted it, so the diagnostic message reports confirmed progress and asks the user to inspect the design before retrying. Large active transfers refresh their one-hour inactivity timeout.

## Updating an existing installation

Run `git pull` and restart the local launcher. If the helper was loaded from `ProxyFoundry/extension`, click **Reload** on its Edge/Chrome extensions page, then reload the Bulk Proxy Forge page. If it was loaded from a separately extracted helper folder, replace the files in that same folder with the updated helper and click Reload. Uninstalling is not necessary.

Small orders remain compatible with installed 1.0.0 helpers. For a large order, the workspace identifies an older helper and asks for this one-time update rather than silently sending an incomplete package. The existing single-ZIP transfer endpoint is retained for compatibility.

## Validation

Unit/API tests cover exact size boundaries, intact pairs and PNG bytes, generated ZIP CRCs, original-snapshot preservation, random ranges across headers and payloads, source offsets beyond 4 GiB, invalid ranges, authorization and expiry. Browser tests exercise the real installed extension against a controlled TCGPlaytest-like importer, including sequential append and cancellation/failure. Controlled tests do not establish an undocumented live-printer maximum.
