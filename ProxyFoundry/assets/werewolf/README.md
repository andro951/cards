# Approved Werewolf header

The reflected title pinlines and four-output-pixel black outline reproduce the
approved nonlegendary previews. `scripts/build_werewolf_assets.py` builds these
once from the pinned CardConjurer front frames and pinline mask. Both faces use
this symmetric header, with the existing native sun/moon icons at native bounds.

`IconRing.png` is the native 129 × 129 circular surround, placed at (80, 97)
on CardConjurer's 1500 × 2100 coordinate grid. Runtime desaturates only its red
donor fringe and caches the processed copy locally. Neutral paint, shading,
geometry and alpha are preserved; the bundled source remains unchanged.
`LowerMask.png` restricts the Godzilla body to the type/rules area and excludes
its original title pinline. The browser reuses bundled assets; no per-card image
reflection or conversion is necessary.

Title paint comes from the native Godzilla title, clipped to the DFC opening.
Back-face title interiors receive native colored back-frame material through a
locally cached operation; bevels, outlines and the true-name strip are retained.
Back type fills are colored in every legendary/nickname combination. Main title
text has a black outline in every combination.

Legendary faces without nicknames use the native floating transform crown with
its circular opening. Right-arrow backs reflect only that crown locally.
Legendary Werewolves with nicknames use the same native joined transform crown
and restored Godzilla bevel treatment as other DFCs, with a genuine circular
opening and attached true-name strip. The sun/moon remains on the left; native
Godzilla title material fills the opening, colored on the back.
