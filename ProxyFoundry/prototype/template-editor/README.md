# Template editor prototype

A separate browser app for creating and editing normal card templates. It does not open, modify or generate production decks.

## Run

Open `START_TEMPLATE_EDITOR.pyw`, or run:

```powershell
python prototype/template-editor/server.py
```

Open http://127.0.0.1:8778/. The local host only serves this prototype and pinned upstream images/fonts. Editing, fitting, compositing and JSON/PNG export happen in the browser. First use of a variant needs internet access; assets are cached in the system temporary directory. The production workspace is never used.

## What you can edit

- Existing M15 sheets and their Border, Frame, Rules, Title, Type and Pinline masks.
- PT boxes, crowns, crown cover/cutout, subtitle, rules divider, artwork, watermark and set-symbol slots.
- Each image variant independently, plus custom images shared across colors.
- Relative anchors, text regions, fonts, colors, outlines, sizing, wrapping, opacity, visibility, layer order and two-color pinline/crown treatments.
- Preview card text, mana, legendary status and nickname. Native mana icons also work inside rules text.
- Drag a selected region to move it. Numeric inspector controls change its relative bounds. Editing a shared anchor moves all attached elements.
- Undo/redo, browser autosave, JSON import/export, a JSON viewer, and 2000 by 2800 PNG downloads without guides.

## Image sizing

The canvas is fixed at 5:7. Full-card frame layers and masks keep their complete coordinate space. Other images fit inside a default region with their aspect ratio preserved: width or height reaches the region boundary first. Scale 1 means the default fit; higher/lower values scale proportionally around the center.

For Title, Type, Rules, PT_Box, Crown and Subtitle, **Upload standalone piece (all colors)** trims transparent padding, clears the old full-card mask, and uses the corresponding default region. It works even if the visible piece was uploaded on a mostly transparent full-card canvas. Original image data stays intact; dimensions and alpha bounds are recorded in assetMetadata. Pixels with alpha below 2 of 255 are ignored for the visible bounds.

**Replace variant image** replaces only the selected color's image while preserving the current alignment and mask. Shared image maps are copied for that part before editing so other parts are not unexpectedly changed. Use **Existing image set: FrameImages** to return to a native full-card sheet and its matching mask. New masks always use full-card coordinates. Cutout compositing erases the frame group, never the artwork.

Disable transparent trimming to preserve intentional padding. Choose full-card alignment when a piece was intentionally positioned on a complete card canvas. Non-5:7 full-card images show a warning; check their preview alignment.

## JSON format

`default-template.json` is the usable version 2 prototype format. The older document in docs/template-editor-prototype is an archived design draft and is not importable here. Version 2 uses a fixed canvas convention, named relative anchors, an ordered parts list, shared asset IDs and color maps. Frame sheets remain full-card even when text is anchored to a small logical region.

Uploaded images are embedded automatically. Check **Embed all template images** to include native frame images and masks too; this downloads unused color variants and makes a larger file. Fonts remain named built-ins supplied by the host. Native references resolve through the pinned provider recorded in provenance. No upstream renderer code is copied into this prototype. Review upstream image/font licensing before redistributing a bundled asset collection.

The prototype's Canvas renderer supplies both its preview and PNG export. It is not yet an adapter to the production CardConjurer renderer; production integration and specialty layouts require a later migration and comparison pass. Images are composited in listed order inside the frame group, with artwork below and text/symbols above. This grouping intentionally prevents cutouts from erasing art or text. Rules and flavor share measured flow by default; disable that checkbox to position either independently.

## Tests

```powershell
node --test prototype/template-editor/tests/model.test.mjs
.venv/Scripts/python.exe -m pytest prototype/template-editor/tests/test_editor.py -q
```

The browser tests exercise actual upstream assets, geometry, uploads, transparent cropping, text/mana collisions, JSON/PNG downloads, undo/redo, persistence and invalid imports. Their host uses a random port and temporary test images. They do not use your real decks.

Revisit supported card types versus specialty overlays after the normal-card editor is settled.