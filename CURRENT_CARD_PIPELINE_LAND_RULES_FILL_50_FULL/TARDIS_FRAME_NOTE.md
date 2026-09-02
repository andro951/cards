# Optional TARDIS frame treatment

The compiler currently treats **The Fourteenth Doctor** as an ordinary multicolored
legendary creature. There is intentionally **no automatic name check** for a TARDIS
frame.

A TARDIS-style legendary-creature template is already embedded in the compiler as:

`layout: "tardis_legendary_creature"`

It uses Card Conjurer's `/img/frames/tardis/` frame family, including the TARDIS
legend crown and TARDIS power/toughness treatment.

If this special treatment is wanted again later, use it only as an explicit
per-card `layout` override (or add a deliberate project-level rule). Do not make
Doctor cards automatically use it merely because they have the `Doctor` subtype.

Current default for The Fourteenth Doctor:
- normal legendary creature frame
- normal multicolored treatment from its actual colors
- standard 1737 px normal-frame set-symbol X position
