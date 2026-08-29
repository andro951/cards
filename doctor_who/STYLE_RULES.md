# Doctor Who project rules

Read `../STYLE_RULES.md` first. This file contains Doctor Who-specific rules only.

## Project source of truth

- Project folder: `doctor_who/`
- Card Conjurer file: `doctor_who/doctor_who_cards.cardconjurer`
- Art folder: `doctor_who/art/`
- Set-symbol folder: `doctor_who/set_icon/`
- Current project size: **50 card-list slots / 51 Card Conjurer faces** because `Esika, God of the Tree // The Prismatic Bridge` is represented as two faces.
- GitHub `main` is authoritative.

## Assets

Art URL pattern:
`https://raw.githubusercontent.com/andro951/cards/main/doctor_who/art/<filename>.png`

Set symbols:
- mythic: `doctor_who/set_icon/mythic.png`
- rare: `doctor_who/set_icon/rare.png`
- uncommon: `doctor_who/set_icon/uncommon.png`
- common: `doctor_who/set_icon/common.png`

Preserve the numbered art filenames. In particular, the modal pair is `12A_Esika_God_of_the_Tree.png` and `12B_The_Prismatic_Bridge.png`.

## Mechanical and flavor text

- Real card mechanics always use current Scryfall Oracle text.
- If an official Magic printing of the card supplies flavor text selected for this project, append it to the Rules Text field using Card Conjurer's `{flavor}` separator, exactly like the Derevi project.
- Do not invent flavor text for this project.
- Flavor text is printing-specific; mechanics are not. Do not replace current Oracle wording with old printed wording merely to match a flavor-bearing printing.
- Normalize unsafe punctuation for Card Conjurer after retrieval.

## Ordinary nonlands

Ordinary nonlands inherit the repository M15 geometry and footer convention.
- Enchantments use Nyx.
- Legendary permanents get the appropriate crown.
- `K-9, Mark I` uses artifact body + blue pinline + artifact legendary crown/P-T.
- `RMS Titanic` uses the Vehicle frame/P-T plus artifact legendary crown.
- `Wedding Ring` is not legendary; it uses an artifact body with a white pinline and no crown.
- Dense rules text should use a smaller font rather than overflowing. `Morophon, the Boundless` is an explicit example: keep the five colored mana symbols inside the rules box and allow a deliberate line break before the five-symbol group if needed.

## The Fourteenth Doctor

Keep Card Conjurer's native TARDIS (WHO) showcase treatment:
- `version = "tardis"`
- `/img/frames/tardis/` assets
- package-native art/text/set-symbol geometry, multicolor frame, P/T and legendary crown.

## Esika // The Prismatic Bridge

Both faces use the real Modal DFC package (`version = "modalRegular"`).

Front (`Esika, God of the Tree`):
- green Modal front frame + modal green legendary crown
- compact opposite-face helper: `Enchantment` and `{W}{U}{B}{R}{G}`

Back (`The Prismatic Bridge`):
- use the native multicolor Modal **back** frame for every back-face component (Flipside, Pinline, Title, Type, Rules, MDFC Arrow, Frame, and Border) plus the modal multicolor legendary crown
- do **not** hybridize the back face with M15 Nyx assets; the official Kaldheim MDFC back uses the native gold Modal back treatment
- compact opposite-face helper: `God` and `{1}{G}{G}`

Do not put the full opposite face name/type in the tiny MDFC helper ribbon. Use the package's real Flipside/MDFC Arrow masks so the helper does not overlap itself.
Reserve vertical space above the helper ribbon: the rules/flavor box must end before the ribbon so flavor text never prints through the opposite-face helper. On the Bridge back face, use the native Modal multicolor back asset throughout so the gold back frame, title/type/rules panels, and back-face indicator all render as one coherent official-style treatment.

## Land text geometry and alignment

Doctor Who lands use light rules text over translucent colored land panels.

For standard Generic Showcase lands:
- `version = "genericShowcase"`
- `artBounds = {x:0, y:0, width:1, height:0.9224}`
- rules text inset is intentionally increased to `x=0.105`, `width=0.79` so text has approximately the same perceived side padding as normal M15 cards.
- all land rules text is vertically centered; do **not** set `noVerticalCenter=true`.
- normal Oracle rules text is left aligned.
- parenthetical mana/tap reminder lines are centered horizontally using `{center}...{left}` inline alignment when Oracle text follows.
- if a reminder is the only text, center the entire reminder horizontally and vertically.

### White land fill opacity

White land rules-panel layers keep their white asset but use **`opacity: 85`**. Do not darken/recolor the white asset and do not lower the opacity of the white pinline. This lets the art show through enough for white rules text to remain readable.

### Fetchlands

Fetchlands use two-color pinline/rules treatment based on the basic land types they search for:
- Flooded Strand W/U
- Scalding Tarn U/R
- Misty Rainforest G/U
- Windswept Heath G/W
- Marsh Flats W/B
- Polluted Delta U/B
- Arid Mesa R/W

Title/type remain neutral land treatment.

### Three-color lands

All three colors must be represented in both pinline and rules treatment:
1. first color base
2. second color with `/img/frames/maskMiddleThird.png`
3. third color with `/img/frames/maskRightHalf.png`

Current ordering:
- Raffine's Tower U/B/W
- Spara's Headquarters W/U/G
- Jetmir's Garden G/W/R
- Zagoth Triome G/U/B
- Indatha Triome B/G/W
- Ketria Triome U/R/G
- Raugrin Triome R/W/U

### Five-color / rainbow utility lands

Five-color utility lands use Card Conjurer's **multicolored/gold land treatment** for pinline and rules background while keeping neutral land title/type treatment. Current project members:
- Crystal Quarry
- The World Tree
- Cascading Cataracts
- Reflecting Pool
- Plaza of Heroes
- Mana Confluence

### Compact land boxes for genuinely sparse cards

The project remains true-borderless Generic Showcase. For cards with almost no text, use the repository's **compact borderless hybrid** rather than the full M15 Extended Art (Shorter Textbox) frame.

Project-specific geometry:
- `version = "genericShowcase"`
- keep full-art `artBounds = {x:0, y:0, width:1, height:0.9224}`
- keep neutral Generic Showcase title and bottom/footer border
- borrow only the short package's `pinline.svg`, `type.png`, and `text.svg` lower-box masks/assets
- never add the short package's `frame.svg` or conventional outer border
- type `y=0.61`
- rules `x=0.105`, `y=0.6743`, `width=0.79`, `height=0.2448`
- set-symbol bounds use `y=0.6343`
- reminder-only rules text is centered horizontally and vertically

Current compact cards are **only** the very sparse lands:
- Forest, Mountain, Swamp, Plains, Island
- Savannah, Tundra, Tropical Island

`Gaea's Cradle`, `Reflecting Pool`, and `Mana Confluence` have real Oracle/flavor content and therefore use the normal Generic Showcase lower box. `Reflecting Pool` and `Mana Confluence` retain the multicolored/gold five-color treatment; `Gaea's Cradle` retains the floating neutral land legendary crown.

## Footer and validation

Footer remains `ChatGPT` / `Custom Proxy • Personal Use Only`.

Before completion validate:
- exactly 51 unique faces in intended order
- current Oracle text preserved
- official selected flavor text uses `{flavor}`
- no land rules object uses `noVerticalCenter`
- land side padding uses the project inset
- white land Rules layers use opacity 85 but white pinlines do not
- all seven fetches have their two searched colors
- all three-color lands contain Middle Third + Right Half masks
- all five-color utility lands use multicolor/gold pinline and rules treatment
- compact land cards use the short-box package listed above
- Morophon's W/U/B/R/G cost reduction stays inside the rules area
- Esika/Bridge use compact opposite-face helper text without overlap
- no temporary updater/workflow remains after any large-file update fallback.
