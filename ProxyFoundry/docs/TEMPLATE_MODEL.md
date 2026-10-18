# Reusable template model v3

Templates import/export as `bulk-proxy-forge-template` with `schemaVersion: 3`. Version 2 files migrate while preserving their regions and offsets. Legacy CardConjurer templates still render through their existing path; convert their source to edit with the new model. Vendor code remains pinned and unchanged.

## Regions and layout families

`data` contains the CardConjurer frame/style source. `groups` declares compatible structural groups, and `baseGroup` selects the editing sample. Regions bind text boxes to semantic fields (`title`, `type`, `mana`, `rules`, `flavor`, `pt`, `loyalty`, `defense`) or a native slot such as `native:ability2`. Source card-specific text and media are cleared during conversion.

Calculated geometry copies the matching native slot's position, size and dimensions. Fixed geometry retains the source layout. Both permit normalized offsets. Separate flavor binding prevents flavor from also being appended to rules. Station templates calculate threshold values and abilities from the actual card, including Station lands. Token styles use `layoutMetadata.tokenStyle` to select classic, full-art or borderless native layout calculation.

A structural group declaration does not create a renderer for an unsupported family. Native geometry requires a compatible built-in layout; otherwise use a complete fixed custom frame and all required semantic/native bindings. Missing mappings and unsupported sample families fail before preview approval. Templates supporting different structures must contain their text slots and appropriate frame variants.

## Geometry formulas

Each region can have `formulas` for `x`, `y`, `width`, `height` and `size`. Supported variables are `native.x/y/width/height/size` and `card.titleLength/rulesLength/colorCount/legendary/hasPT`. Arithmetic supports `+ - * /`, parentheses, `min`, `max`, and `clamp(value, low, high)`. This is a checked arithmetic grammar, not Python or JavaScript execution. Formula length/complexity, nonfinite results, division by zero and unbounded region geometry are rejected.

```json
{"field":"title","geometry":"native","offset":{},"formulas":{"width":"clamp(native.width - card.titleLength * .001, .2, .9)"}}
```

## Conditional variants

`variants` is an ordered array of at most 32 objects. `when` can match `group`, exact `colors` (W/U/B/R/G list), `legendary`, and `hasPT`. A variant replaces `frames`, individual `regions`, or both. The first match wins. Conditions fully hidden by an earlier variant are rejected.

```json
{"when":{"colors":["U"],"legendary":false},"regions":{"title":{"field":"title","geometry":"native","offset":{"y":0.005}}}}
```

Generate template preview validates each claimed group plus the variant conditions. Provide sample card names or exact printing IDs for families without a default sample; additional samples are mapped by group. Sample selection displays each rendered result and its calculated region outline. Editing after validation invalidates approval; saving requires another preview. Closing cancels work. Uploaded frame assets, including variant layers, travel in portable JSON exports with hash checks.

Static CardConjurer source choices are selectable immediately. Generate source previews is optional; importing or choosing a source does not render automatically.