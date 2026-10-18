# Behavior and requirements reference

## Product and intended workflow

Bulk Proxy Forge imports Magic decks, resolves card data and printings, applies art and templates, generates proxy images, reviews warnings, and exports paired fronts/backs for printing. It must run as a free static website without a hosted application server. A double-click local static preview launcher is allowed; the original Python launcher remains separately available.

The intended sequence is collect input, choose Normal Look or Customize Look, finish relevant setup, generate images, review, then export. The Add New Deck modal remains small. Normal Look means ordinary MTG art and normal frames, including lands. Customize exposes art, frames, symbols, backs, credits, and per-card choices. The original request allowed Normal Look to prepare automatically after selection; the subsequent broad instruction forbids generation before Generate Images. That exception needs a product decision before changing it.

Template selection must use static card-back placeholders until supplied samples arrive. Selecting a frame must be immediate and must not start rendering. This supersedes earlier requests for generated picker previews. Card Conjurer source-import previews are a separate workflow and should not be confused with ordinary frame selection.

## Required data behavior

Preserve exact printings where supplied; resolve names through Scryfall otherwise. Outside-the-game cards are included by default with a user opt-out. Unsupported cross-origin deck sites use an optional browser helper or file export; the removal of server adapters is intentional. Add sites only after verifying that the client-side or helper path works.

Custom art comes from local files or GitHub. One-click import gathers art and associated data.json, symbols, and backs. Number-prefixed image names should match safely without overriding exact matches or choosing ambiguous names. data.json carries nickname, flavor, and artist information through manual file, GitHub link, and one-click paths. Custom-art credits are required. Fallback art defaults OFF under the final decisions, despite an earlier contradictory paragraph.

Canonical card data and nullable manual overrides remain distinct. Art selection and printing selection remain independently editable. Specialized Prepare, Station, transform, helper, token, and nickname cards need compatible structural frames and useful failures when unsupported. Station lands now use the ordinary Station frame. Godzilla power/toughness belongs above the normal layer. Tokens expose classic arched and newer full-art/borderless families with suitable text layouts.

## Review and cache behavior

Setup edits mark affected renders stale but retain the previous image for inspection. Only affected faces should regenerate. Version changes should invalidate the relevant cache scope. Crop warnings block checkout, not ordinary editing; acknowledgement belongs to a specific render key and expires when that render changes.

Review supports full-screen images, continuous navigation, front/back pairing, common backs once and distinct backs where needed. Export orders capture immutable render selections. Small individual images use the browser's ordinary download behavior; large exports may request a destination. No mandatory print helper installation.

## Templates, presets, storage, and backups

Reusable templates need versioned semantic regions, dynamic geometry, formulas/variants where required, validation, and dependency protection. Card Conjurer conversion must remove card-specific art/symbols/text while preserving reusable structure. Ordinary layouts are only the first portion of the requested model; unsupported structural families must not be offered as working editor seeds.

Presets are named portable style settings. Saving a preset must not silently make it the default. A default preset is optional. Its priority against Normal Look's promise needs definition.

Browser-managed storage is the latest default; a chosen local folder is optional. Remember folder choice and recover permissions explicitly. Do not silently open another workspace if permission expires. Backups select objects, optionally include generated files, estimate size, and replace confirmed collisions rather than merge unpredictably. Permanent deletion was requested; a trash system should not be restored as an unsolicited rollback.

## Current implementation

The current site retains the Python workspace/domain/compiler through Pyodide in a Web Worker. A service worker bridges HTTP-shaped requests from existing UI and rendering code. Python runs against a synchronized in-memory filesystem mounted from OPFS or a folder handle. Card Conjurer remains the pinned renderer with adapters. The local baseline ran the same workspace through a Python HTTP server and threaded jobs, with an ordinary filesystem.

This preserves much domain code, but it does not preserve background job semantics or filesystem memory costs. Those are central to the reported loss of reliability. Current source confirms synchronous browser jobs and memory-backed file synchronization; it does not establish the exact cause of the reported mid-deck crash.
