Approved compact full-art land header parts

Rebuild with: .venv/Scripts/python.exe scripts/build_land_join_assets.py
Sources are fetched through Runtime from the pinned CardConjurer snapshots.
geometry.json stores cropped asset placement on the 2010 x 2814 canvas.

Nonlegendary + nickname:
  Native nickname addon cropped at source row 148 (inner top outline).
  Native title stays intact, above the true-name bar in the layer order.
  Trim the addon against the title silhouette, ignoring faint resize halos.
  Crop its first occupied output row, then move the addon up two output pixels.
  Keep the small seam overlap; do not retrim after the move.
  Preserve native alpha and shading; match only colored rim pixels.
  No horizontal blending. True-name text follows the two-pixel move.

Legendary without nickname keeps the normal native floating crown with the
approved black contour. Legendary with nickname uses the native Godzilla
joined crown; no cropped addon is stacked on top of it.

The rounded Temple family is preserved in the vendor compiler. To restore it:
  1. Uncomment its 'land' selector entry in foundry/compiler.py.
  2. Remove 'land' from RETIRED_BUILTINS.
  3. Remove the documented automatic compact-land routing override.
No native assets or original rounded recipes were removed.
