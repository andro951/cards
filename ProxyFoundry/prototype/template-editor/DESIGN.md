# Template Studio v2

## Creator walkthrough

The card remains visible beside a single working panel. Five freely selectable steps replace three competing inspectors. Editing never waits for previews. Undo, redo and autosave apply throughout. Renderer IDs, normalized coordinates and script paths are not normal editing controls.

1. **Start.** Name the template. Start from the pinned M15 images and masks, reopen an editable template, or supply a custom frame sheet. A custom sheet can use the existing masks to separate editable parts, or remain a single complete frame. The 5:7 canvas is fixed. Artwork is a preview input, never baked into the template.
2. **Parts.** Select Border, Frame, Pinline, Title, Type, Rules, Crown, Subtitle or Power/toughness. Upload a replacement, move or resize it, and choose when it appears. Standalone pieces remove practically transparent padding and fit their normal role while keeping proportions. Full-card sheets keep their alignment. Text follows the shared region; individual text adjustments remain possible. Advanced settings expose masks, stacking and cutouts.
3. **Colors.** Choose one unchanged image, one recolorable image, or individual images. Recoloring is explicit, preserves transparency and texture, and previews every treatment. Individual assignments show filenames and missing slots. Reusing an image for unprovided colors is an explicit choice. Two-color pinlines and crowns are checked too.
4. **Text.** Select a named text region on the card. Use simple font, size, alignment, color and outline controls. Test short and long rules, mana, nicknames and legendary/nonlegendary cards. Automatic fitting and mana/set-symbol reservations remain automatic.
5. **Review.** Show representative cards, coverage and layout warnings. Export a portable main-app template and an editable source. Export is blocked for missing assignments, unsupported content or unacknowledged overflow. No silent substitutions.

Existing-frame creators usually start from M15, replace only desired parts, adjust text and review. A one-image creator uploads their complete neutral sheet, chooses existing masks or a complete overlay, then chooses recoloring or unchanged reuse. A per-color creator assigns images to the named color slots and explicitly chooses any shared fallbacks. All three paths end in the same editable definition and production export.

## Import contract

The production export retains the existing version 3 envelope and adds a validated visual recipe. Images/masks/crops/color blends are resolved by the editor into portable PNG layers; the app chooses their color and appearance conditions and binds actual card text. CardConjurer still performs final rendering. This avoids teaching its renderer another file format or copying its implementation. Editor-only sample artwork is excluded. A source definition accompanies the export for reopening.

## Verification plan

- Unit tests: fitting, coverage, color assignment, recoloring, recipe validation and card binding.
- Browser workflows: native M15, custom single recolorable sheet, per-color pieces, masks, undo/redo, persistence, import/export and responsive layouts.
- Production tests: the real import method, compiler output for ordinary cards, color pairs, nickname and legendary/PT conditions, native runtime rendering.
- Visual checks: desktop and smaller screens, gallery and exported/native examples; compare geometry and layers against editor output.
- Measure warm preview latency and export progress; preserve input while loading. Re-evaluate after each test pass and document remaining scope honestly.

Specialty structures and type eligibility are deliberately deferred until the normal template workflow is proven. No holofoil stamps.