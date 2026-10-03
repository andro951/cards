# Frame components and actual color coverage

## Contract

A complete base image can and should be preserved. Native masks can expose pinline, title, type and rules overlays above that image. Separate components are required for independent recoloring; visible boxes embedded in a full image do not mean those components are independently wired. Crown compatibility must be evaluated by frame geometry, not merely the Legendary supertype.

The app DOES have a final universal pass: `foundry/compiler.py::apply_universal_frame_color_treatment`, called by `Compiler.compile_face` after structural selection. It processes existing mask layers and recognized crown families; it does not create missing components. Exactly two colors use the approved gradient pinline and two native crown images. Title/type/rules use mono color or multicolor/gold; land semantics use land_colors.

Correction to the earlier conversation: native planeswalker recipes return early from native recipe_data, but the app's final universal pass STILL runs. The actual failure is missing exposed components. An early return is not the complete explanation.

## Coverage matrix

“Exposed” means independently usable in the current builder, not merely visible in the final base PNG. “Upstream” means the live pack declares the component, not a claim that all masks have been visually verified.

| Card/frame family | Pinline | Title/type graphics | Legendary treatment | Assessment |
| --- | --- | --- | --- | --- |
| Creature, Instant, Sorcery; Kindred/Tribal underlying spell | Exposed native masks | Exposed native masks | M15 crown when legendary | Present; compiled two-color probes confirm pinline and dual crown layers |
| Artifact, artifact creature, Equipment | Exposed native masks | Exposed native masks | M15 crown when legendary | Present; body remains structural artifact, final mask sources receive shared semantics |
| Nyx Enchantment and combinations with Artifact/Creature | Exposed native masks | Exposed native masks | Outer crown when legendary; inner crown families recognized by shared pass | Present; actual automatic recipes do not always install Nyx inner crowns—recognition alone is not installation |
| Vehicle | Exposed native masks | Exposed native masks | M15 crown when legendary | Present; compiled legendary and nonlegendary two-color probes |
| Nonlegendary full-art lands, original duals, tri/five-color | Native recipe owns colored inline components | Separate/combined inline bars | Not applicable to nonlegendary | Present through specialized builders; not everything uses universal mask dispatch |
| Legendary full-art lands | Exposed pinline | Exposed/inline title and type | Native floating crown, dual/tri blend | Present; compiled dual-land probe confirms dual crown |
| Basic/Snow lands | Native full-art basic Pinlines mask (plural) | Embedded in complete native frame | No automatic crowned-basic variant | Existing whole-frame color treatment; universal detects plural pinlines but native textless recolor family is not mapped |
| Transform front/back; Meld | Converted native pinline masks | Converted native title/type/rules | Converted native transform crowns | Component path present; preserve face-specific geometry and icon strip |
| Approved Modal DFC pairs | Native masked components | Native components, plus opposite-face reminder | Modal crown present in approved templates | Partial universal family dispatch: _frame_effect_source has NO modal source case; dedicated modal semantics handles native bars, but a mono-color artifact body/title/type discrepancy needs a real fixture check |
| Regular 3-ability planeswalkers | Upstream mask exists; builder exposes NONE | Upstream Title/Type exist; builder exposes NONE | No standalone crown installed | Confirmed missing wiring |
| Tall 4-ability planeswalkers | Upstream tall pinline exists; builder exposes NONE | Upstream Title/Type exist; builder exposes NONE | No standalone crown installed | Confirmed missing wiring; tall sources also missing from shared recolor dispatch |
| Saga | Dual overlay exists; mono embedded in base | Upstream Title/Type exist, embedded in base | No legendary crown added by Saga builder | Dual pinline/tassels handled; legendary Saga styling needs compatible treatment decision |
| Saga Creature, including trailing rules | Dual overlay exists; complete short base preserved | Upstream Title/Type exist, embedded in base | No legendary crown added by Saga-Creature builder | Same coverage limitation; preserve short frame geometry |
| Station/Spacecraft and station lands | Explicit overlay ABOVE complete Station frame | Native donor title/type masks BELOW complete Station overlay | Crown remains above overlay | Pinline/crown present. Title/type recoloring may be obscured by neutral full overlay; requires visual fixture before calling it correct |
| Prepare host | Exposed native mask | Exposed native masks | No crown installed in approved Prepare seed | Host pieces present; nested spell pinline currently uses host semantic colors, not separate nested-spell policy |
| Classic arched token; modern full-art token; borderless token | Dual overlay exposed for multicolor; mono embedded base | Native Title/Type exist; embedded full base | Floating crown addon for legendary tokens | Dual pinline and crown supported; complete texture preserved, not independently exposed title/type |
| Godzilla nonland/land, including allowed DFC variants | Upstream native mask exists, new base exposes NONE | Type embedded; separate generated Title/Crown | Generated proxy-foundry Crown images | Confirmed late replacement loses universal treatment; generated crown family not recognized |
| Flip | Upstream pinline.svg exists; builder exposes NONE | Two sets of text slots, native pack exposes combined Twins graphics, not separate Title/Type masks | No added native legend-crown layer | Missing dual pinline wiring; cannot reuse ordinary M15 title/type/crown geometry blindly |
| Class | Upstream pinline/Title/Type/Rules masks exist; builder exposes NONE | Embedded complete Class PNG | Legendary Class explicitly rejected | Confirmed missing dual pinline; newer upstream pack offers nyx sources while current builder uses class/*.png—do not switch families without review |
| Battle | Upstream pinline exists; builder exposes NONE | Upstream Title/Type/Rules exist; builder exposes NONE | No crown installed | Confirmed missing dual pinline wiring; rotated geometry matters |
| Emblem | Fixed native emblem full frame | Embedded emblem visuals/text | Not applicable | Fixed specialist design, not ordinary WUBRG recoloring |
| Helper/Day-Night/trackers and Art Series | Full-card artwork/scan, no conventional component contract | Scan/custom helper | Not applicable | Explicit exception |
| Prototype | Recognized group uses underlying native build path | Underlying recipe | Underlying recipe | No separate prototype frame implementation; do not treat this as a verified prototype-layout inventory |
| Case, Room, Split/Aftermath, Adventure, special lands, planar/Phenomenon, Scheme, Vanguard, Dungeon, Conspiracy | Custom template required | Custom template required | Custom capability required | Not built-in coverage; capability depends on supplied template |

Snow/World modifiers inherit their underlying type. Land Creature and Enchantment Land need special treatment: Enchantment Land delegates to the land builder; other unsupported combinations must not silently invent a frame. Uploaded templates may include any native component, but shared dispatch only supports recognized source families and mask names.

## Upstream evidence

Live pack URLs: https://cardconjurer.app/js/frames/packPlaneswalkerRegular.js ; packPlaneswalkerTall.js ; packM15Regular-1.js ; packM15Nyx.js ; packM15LegendCrowns.js ; packM15LegendCrownsFloating.js ; packM15InnerCrowns.js ; packSagaRegular.js ; packSagaCreature.js ; packStationRegular.js ; packPrepare.js ; packBattle.js ; packClass.js ; packFlip.js ; packM15Nickname.js ; packM15TransformFront.js ; packM15TransformBackNew.js ; packTransformLegendCrowns.js ; packModalRegular.js ; packModalLegendCrowns.js ; packGenericShowcase.js ; packM15BoxTopper.js ; packTextlessBasics.js ; token packs listed in upstream-components.json. All pack filenames resolve under the same /js/frames/ base. Initial guessed 404 names were replaced with names read from frameSearch.js; they are not evidence of missing assets.

## Evidence and limits

compiled-probes.json contains 38 successful final Compiler.compile_face outputs covering ordinary type combinations, two planeswalker geometries, Saga, Class, Battle, land variants, Godzilla and six token modes. native-layouts.json covers preserved seed layers, including modal and Prepare. upstream-components.json records declared mask/component names for the live packs. Station, transform, modal, Saga Creature and Flip were additionally traced in source; no new rendered outputs were generated for this audit.
