from pathlib import Path

ROOT_BLOCK='''

## Borderless land text/readability conventions

For projects using light text over translucent full-art land panels:

- Land rules text should be vertically centered unless a project explicitly documents a different layout.
- Parenthetical mana/tap reminder text should be horizontally centered. If it is the only rules text, center it horizontally and vertically.
- When a centered reminder precedes normal Oracle text, use Card Conjurer inline alignment (`{center}` for the reminder, then `{left}` for the Oracle text) rather than centering the Oracle text.
- Projects may increase the Rules Text horizontal inset when the native Generic Showcase geometry visually crowds the border; record the exact project geometry in the project rules.
- For **white** Generic Showcase/land Rules fills used with white rules text, preserve the white asset hue but use **`opacity: 60` on the white Rules layer only**. Do not reduce opacity on the white pinline. This is the standard white-land readability override unless a project explicitly chooses another value.
- Five-color/rainbow utility lands should use Card Conjurer's native multicolored/gold land treatment for pinline and rules-panel color rather than a neutral gray land treatment.

### Shorter land text boxes

Card Conjurer's M15 Extended Art (Shorter Textbox) package may be intentionally used for sparse lands when a project prefers a smaller type/rules area. This is a deliberate presentation choice, not the same layout as Generic Showcase borderless.

Native recipe:
- `version = "m15ExtendedArtShort"`
- `artBounds = {x:0, y:0.081, width:1, height:0.5753}`
- set-symbol bounds use `y=0.6343`
- type `y=0.61`
- rules `y=0.6743`, `height=0.2448`
- masks: `/img/frames/m15/boxTopper/short/pinline.svg`, `/type.png`, `/text.svg`, `/frame.svg`, plus normal title/border masks
- land assets: `l.png`, `wl.png`, `ul.png`, `bl.png`, `rl.png`, `gl.png`, `ml.png` under `/img/frames/m15/boxTopper/short/`

If a project combines this family with split-color land treatments, use the same Right Half / Middle Third masking principles as its documented land recipe and keep any white Rules layer at the standard white-land opacity override.
'''
DEREVI_BLOCK='''

## White borderless-land readability override

For Derevi's true-borderless Generic Showcase lands, a white Rules-panel fill keeps the normal white frame asset but uses **`opacity: 60`**. Do not recolor the white asset and do not lower the opacity of the white pinline. This is specifically a Rules-panel readability adjustment for white text over white-associated translucent fills.

All Derevi land rules text is vertically centered. Sparse mana reminder text remains horizontally centered; ordinary Oracle rules text remains left aligned.
'''
for path,marker,block in [(Path('STYLE_RULES.md'),'## Borderless land text/readability conventions',ROOT_BLOCK),(Path('derevi/STYLE_RULES.md'),'## White borderless-land readability override',DEREVI_BLOCK)]:
    text=path.read_text(encoding='utf-8')
    if marker not in text:
        path.write_text(text.rstrip()+block+'\n',encoding='utf-8')
print('style rule append complete')
