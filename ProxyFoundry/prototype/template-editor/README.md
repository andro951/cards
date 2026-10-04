# Template Studio

A separate browser app for designing normal-card templates, with portable exports that the real BulkProxyForge app can import. The production app still uses CardConjurer for final rendering.

## Run

Open `START_TEMPLATE_EDITOR.pyw`, or run:

```powershell
python prototype/template-editor/server.py
```

Open http://127.0.0.1:8778/. The previous advanced prototype is retained at `/classic`.

The loopback host serves the editor and pinned upstream images/fonts. Editing, fitting, previews and export happen in the browser. First use needs internet access; upstream assets are cached in the system temporary directory. Testing and editing do not modify production decks.

## Creator workflow

The card stays visible beside five freely selectable steps. There is no Save button: the draft autosaves in this browser, and Undo/Redo work throughout.

1. **Start:** Use existing M15 sheets and masks, reopen a template, or upload a transparent custom full-card sheet. Choose existing M15 masks to split a compatible sheet into editable parts; otherwise keep it as one complete overlay. Upload test artwork separately; it never becomes part of the template.
2. **Parts:** Choose a named part, replace its image, move or resize its region, and choose when it appears. Drag on the card or use percentage controls. Text follows the associated region. Advanced controls reveal masks, alignment, stacking and cutouts.
3. **Colors:** Keep one image unchanged, create treatments from one neutral image, or assign separate images per color. Batch uploads suggest colors from filenames, then let you confirm them. Missing assignments block export unless you explicitly choose a shared fallback. Tint masks protect areas that should retain their original colors. Palette changes update recolorable uploads automatically.
4. **Text:** Adjust named text regions, fonts, sizes, alignment and outlines. Mana and set-symbol reservations are automatic. Rules and italic flavor can share automatic flow and a divider, or use independent regions.
5. **Review:** Inspect 24 representative samples, including ten color treatments and all ten two-color pairs. Click a sample to enlarge it. Missing images, incomplete colors and layout warnings block export. Download an importable template or an editable source.

### Using the result

In BulkProxyForge, open **Templates → Import Template** and select the `.bpf-template.json` download. Choose it later in the deck's Art & Setup. The app stores each image once; compiled cards reference stored assets rather than embedding the whole image collection repeatedly.

To edit again, open the downloaded file in Studio. The app's **Export JSON** also preserves the editable source and its images. Studio templates use this editor rather than the older production template inspector.

## Image fitting

The canvas is always 5:7. Full-card frame sheets, borders, pinlines and masks retain their complete coordinate space. Standalone pieces trim transparent padding and fit their normal role proportionally: whichever dimension reaches the region boundary first determines the fit. Very wide or tall pieces are never stretched to fill both dimensions. Alpha values below 2 of 255 are ignored while finding visible bounds; original pixels remain available.

An upload of a standalone rules/title/type/PT/crown/subtitle piece works even when it arrives on a mostly empty full-card image. Choose **Preserve full-card alignment** under Advanced when that padding is intentional. Masks use full-card transparency coordinates. Cutouts erase the frame group, leaving artwork beneath it intact.

Shared color maps are isolated when you replace one part. Replacing the whole sheet intentionally updates its linked parts. Reopening templates and Undo/Redo preserve these relationships.

## Export contract and scope

The editor's source is `bulk-proxy-forge-visual-template`, version 2. Production downloads use the existing `bulk-proxy-forge-template`, schema 3 envelope with a validated `visualRecipe` and `editorSource`. Sources are shared, native sheets/masks remain referenced together, and transformed pieces or color blends are baked into portable image layers. Artwork is excluded. Import normalizes images into content-addressed assets; re-export includes them again.

Supported for this version: ordinary cards, legendary cards, lands, legendary lands and basic lands. Parts include border, frame, pinline, title, type, rules, crown and crown cutout/cover, real-name subtitle, PT, automatic rules divider, artwork placement and set-symbol bounds. No holofoil stamps.

Specialty structures and type eligibility remain deferred. Watermark export, custom divider images, and per-card artwork focus/zoom are rejected explicitly rather than silently omitted. Built-in fonts are supplied by the runtime; the lightweight editing preview and CardConjurer can have small text-metric differences. Final native-render integration is tested separately.

`native-base.json` contains data-only runtime defaults from the app's existing M15 seed. No upstream renderer implementation is copied. Existing image/font provenance is recorded in the seed and host; review their licensing before redistributing an asset collection.

## Tests

```powershell
node --test prototype/template-editor/tests/model.test.mjs prototype/template-editor/tests/workflow.test.mjs
.venv/Scripts/python.exe -m pytest prototype/template-editor/tests/test_editor.py prototype/template-editor/tests/test_studio.py tests/test_visual_templates.py tests/test_template_model_v2.py tests/test_template_model_v3.py tests/test_template_safety.py -q
$env:PF_LIVE_CC='1'
.venv/Scripts/python.exe -m pytest tests/test_visual_template_native.py -q
$env:PF_BROWSER='1'
.venv/Scripts/python.exe -m pytest tests/test_visual_template_website.py -q
```

Tests use temporary workspaces and fresh exports. They cover native and custom images, recoloring, per-color assignment, cropping, shared anchors/maps, conditional layers, text binding, undo/redo, persistence, desktop/smaller layouts, portable round trips, actual static-browser import, and genuine CardConjurer PNG rendering. Performance results are recorded in `verification-v2.json`; generated screenshots live in ignored `test-results`.

The design walkthrough and decisions are in `DESIGN.md`. Revisit supported card types versus specialty overlays after this normal-card workflow is settled.