# Confirmed component gaps

## High: planeswalker masks are omitted
Evidence: native build_regular_pw_3_recipe/build_tall_pw_4_recipe produce complete frames with empty masks. Upstream regular/tall packs declare Pinline, Title, Type. The final pass cannot invent those layers; tall source family is missing from _frame_effect_source. Impact: dual accents remain multicolor rather than approved paired colors. Repair: preserve complete base, expose matching native overlays, add tall recolor family, check frame-specific crown treatment. Test actual final compiled outputs plus rendered regular/tall pairs.

## High: Godzilla replacement occurs after color pass
Evidence: Compiler.compile_face applies universal colors, then apply_nickname_treatment(full_frame=True) invokes _apply_godzilla_frame, replacing frames. New frames have no pinline/type masks, and proxy-foundry/godzilla/Crown*.png is not a recognized crown family. Impact: global colors do not survive explicit Godzilla selection. Repair in adapter; preserve complete base and existing no-real-name behavior, expose native masks, process generated crown assets with correct bounds, run final coloring after replacement before nickname addon. Tests need legendary/nonlegendary, land/nonland, mono/dual and nickname states.

## Medium: Class/Battle/Flip retain complete bases without native dual overlays
Evidence: build_class_data/build_battle_data/native.build_flip_recipe use masks:[]; corresponding live packs have pinline masks. Impact: two-color pinlines cannot receive global gradient. Fix native overlays above complete base, preserving texture; map Flip source family if bar treatment needs recoloring. Legendary Class is an intentional rejection, not silently supported.

## Medium: nested Prepare pinline is conflated with host
_is_pinline_mask accepts any name containing pinline, including Prepare Spell Pinline, and applies host colors. Parent and nested spell may differ. Need explicit nested semantic policy and a mixed-color host/spell fixture before changing it.
