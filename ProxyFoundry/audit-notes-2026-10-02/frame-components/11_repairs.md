# Component repairs — 2026-10-03

- Expose native regular/tall planeswalker, Class, Battle and Flip pinline overlays above their complete base frames. Native title/type/rules geometry stays intact; existing gold boxes remain gold for multicolor cards.
- Map tall planeswalker, Station, Flip and modal front/back sources in the shared effect dispatcher. Opposite-face modal reminder masks remain structural and retain their own face color.
- Expose Station title/type/rules overlays above the complete Station frame; lower donor masks cannot suppress these visible overlays. Colored artifacts retain their metal body and native power/toughness.
- Apply shared coloring after Godzilla frame replacement. Native pinline overlays and two genuine generated crown variants supply the paired colors. Nickname addons remain topmost and power/toughness remains above the base.
- Prepare spell panels use the spell's own colors (explicit Scryfall colors/indicator, or mana symbols when colors are absent), independently of host/body colors. Colorless spells use the neutral native source.
- Template versions invalidate affected cached renders. Complete native bases and preserved vendor sources are unchanged. Reapplying the shared pass does not accumulate overlays.

## Legendary geometry

Planeswalkers use their native integrated upper outline; the regular/tall pinline masks color it. Existing standalone crown families (M15, Nyx, transform/modal, Station and Godzilla) retain their own assets and geometry. Class's existing Legendary validation remains explicit. Saga, Battle and Flip do not have a compatible standalone legendary crown in these selected native packs; this repair does not invent a regular M15 crown over their incompatible layout. Their native title/type/pinline components are preserved and colored.

## Verification

The final compiler matrix covers all ten color pairs across eight repaired families, idempotence, preservation, Station overlay order, Godzilla legendary/nickname states, modal reminder isolation and colorless Prepare spell independence. Actual Chromium/CardConjurer rendering exercises all eight families and checks that the real upstream masks were requested. Saved PNGs were visually inspected, including both planeswalker heights, gold boxes, blue/red pinlines, Station body/crown and Godzilla crown blending. Extended Prepare, Station, Station land and Godzilla checks are recorded in the test reports.
