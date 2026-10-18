Original-dual true-name addons

Rebuild: .venv/Scripts/python.exe scripts/build_land_addon_assets.py
Pinned native M15 nickname addon sources are fetched through Runtime.
Only the outside black contour along the bottom and curved shoulders is
removed. The colored rim, inner outline, translucent fill, original image
dimensions and placement remain intact.

The original-dual type mask is adapted separately in foundry/runtime.py.
Its native fill ends 0.48 SVG units inside the pinline's inner boundary.
A 1.06-unit stroke restores the clipped native frame, allowing a slight
antialiasing overlap with the pinline. No frame image is stretched.

Basic-land nickname join

Rebuild: .venv/Scripts/python.exe scripts/build_basic_land_join_assets.py
BasicTrueName covers the five native EOE colors. The addon is cropped at row
148 (the inner top black contour), at its original scale, shifted upward two
2100-reference pixels from the preceding preview (+1 instead of +3).
Subtitle pixels covered by the native title are removed, except for one
rendered row at the lower edge to cover its faint antialiased seam. Position
is unchanged. Addon rim and interior alpha match the native title separately.
The native title, its masks, opacity, and all other frame layers stay intact.
There is no blending or title cutout. The opaque footer stays behind the addon.
All addons use the native 2010 x 2814 canvas; no runtime image processing.

Basic lands with nicknames raise the complete title group by 24 rendered
pixels at 2010 x 2814 (24/2814 normalized y). Both names, title layers, mana
symbol, subtitle, and set symbol move together. The opaque bottom card border
and footer credits stay fixed. Basic lands without nicknames do not move.
