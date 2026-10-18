# Visual template draft, version 1

Historical design draft. The working separate prototype is in `prototype/template-editor`; its `default-template.json` is the current version 2 format with a fixed 5:7 canvas and image fitting/alpha-cropping rules.

`normal-m15.template.v1.json` is a design proposal for the separate editor prototype. It does not replace the production template model or alter rendering.

## Coordinate and placement contract

The design canvas is 2010 by 2814 pixels. Every rectangle uses fractions of its explicitly named reference rectangle: x/width relative to reference width, y/height relative to reference height. Canvas-relative rectangles therefore use full-card coordinates. Font sizes, divider thickness, and flow gaps marked designPixel scale uniformly with output resolution. A text part uses its own resolved rectangle; font metrics determine the baseline within it.

Anchors are editable logical layout regions. Masked M15 frame images remain full-canvas images: they are not stretched into the logical Title or Rules rectangles. Small native assets such as the PT box and crown use their own placement bounds. Masks explicitly declare canvas coordinates, even when their image layer is small. This distinction prevents the crown-sized-mask stretching issue.

A text rectangle is relative to its anchor. Moving the Title anchor moves its text and mana region together. Moving Type also moves the set-symbol region. reserveSpaceFor reduces the text width using the actual measured occupied bounds of visible symbols, not their entire allocation rectangle. Hidden symbols reserve no space. A relative rectangle can extend outside its parent for an overlay.

## Images and colors

M15 uses a color-specific image sheet plus individual masks for Border, Frame, Rules, Title, Type, and Pinline. Each part selects independently from the sheet. The maps include W/U/B/R/G, Multicolor, Artifact, Land, and Colorless. PT and subtitle/crown assets have explicit fallbacks where they lack the same variant codes.

Image maps use the current upstream resource paths. These paths were read from the existing recipes, not downloaded or copied into this draft. Availability and licenses still need checking before bundling assets with an editor distribution.

For two colors, pinlines use the current palette with a smooth 40%-60% transition. Crowns blend native textured images in the same order. Title, Type, Rules and Frame keep native texture. The prototype must allow editing these policies and maps independently.

Crown_BorderCover is the native black cover rectangle. Crown_Cutout is an optional disabled mask slot. eraseAlpha applies only to the frame composite group, leaving artwork untouched. No stamp or stamp surround is included.

RulesDivider accepts an uploaded image or the configured procedural line fallback. Its position follows the end of rendered rules text. It appears only when both rules and displayed flavor exist.

## Data, conditions and flow

Bindings are declarative descriptions for the draft, not executable expressions. The prototype needs a documented finite binding resolver and condition evaluator. It must reject unknown fields and operators. firstMatch color cases are evaluated in their listed order. Derived values such as frameColors are supplied by card-data preparation, never inferred from the image filename.

Parts are drawn back-to-front in drawOrder. The renderer adapter must reverse the appropriate frame list for CardConjurer. Frame compositing occurs before text, and the subtitle frame is above all ordinary structural frame parts. The watermark is above frame fill and below body text.

RulesContent measures rules and flavor together, omits hidden/empty items and their gaps, inserts the divider between visible items, and fits the text within the allocated area. Its exclusion region avoids the visible PT box. The region and typography may be edited; overflow produces a warning/error instead of silently clipping content.

controls.fullArt selects artwork.fullArtOverride. This changes art fitting to the whole card using the same cover/center calculation. It does not silently modify other frame parts. showFlavorText, showSubtitle and showWatermark drive the documented bindings. Other card settings such as artist attribution remain card/deck data rather than template defaults.

## What still needs prototype verification

Native recipe art, text and PT coordinates were used as starting measurements. Logical anchors, separate flavor layout, footer and subtitle placement are proposals. They have not been rendered as this format has no renderer yet. The editor must show immediate visual feedback and test long content, mana/title collisions, PT exclusions, nickname/crown junctions and multicolor masks.

Supported card types versus specialty overlays should be revisited after the normal-card definition is settled. The schema intentionally does not declare specialty applicability yet.
