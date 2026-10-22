IMAGE FOLDER COMPARE ALL

Double-click ImageFolderCompareAll.exe. No Python installation is required.
It starts immediately and leaves the summary visible until you press Enter.

Keep this folder directly inside your cards repository:
  cards/ImageFolderCompareAll/ImageFolderCompareAll.exe

For each top-level deck folder, the program looks inside its cards/ subfolder:
  cards/Derevi/cards/*.zip

The TWO NEWEST ZIP FILES are selected by ZIP file modification time, not the
timestamps of extracted folders. Filename order breaks exact timestamp ties.
Standalone image folders do not count. Decks with fewer than two ZIPs are skipped.

An existing folder named exactly after a ZIP (without .zip) is reused. Otherwise,
the ZIP is extracted beside itself. Existing extracted folders are never replaced.

Edit blacklist.txt to skip any top-level repository folder. Write one folder name
per line; names are case-insensitive. Blank lines and # comments are allowed.

Results are copied here, grouped by deck:
  ImageFolderCompareAll/diff/Derevi/       changed images from the newer ZIP set
  ImageFolderCompareAll/new/Derevi/        images only in the newer ZIP set
  ImageFolderCompareAll/removed/Derevi/    images only in the older ZIP set

Only nonempty result folders are created. Unchanged decks have no result folders.
Relative image subfolders are preserved. Folders named removed, diff, and new
inside the input sets are ignored at any depth. A single enclosing export folder
is unwrapped automatically for filename matching.

Identical bytes skip decoding. Files whose bytes differ are compared by exact
decoded RGBA pixels, including every animation frame, with EXIF orientation
applied. Metadata/compression-only differences are ignored. This is the same
comparison engine used by ImageFolderCompare.

BulkProxyForge review images (filenames ending in _review, with odd pixel width
for two equal panels and a one-pixel divider) compare only the generated card
on the RIGHT. The reference panel and divider are ignored. Generated-card pixel
and alpha changes are still exact; dimensions changing also counts. Results
contain the full review image. Other images compare every pixel, with no tolerance.

Each successful run REPLACES the prior diff/new/removed results automatically,
including removing categories or decks that no longer have differences. Source
images and ZIPs are kept. If any eligible deck fails, the previous complete result
is kept. Details and skip reasons are written to last-run.txt.

If Windows keeps a result folder open, publication falls back to replacing files
inside the existing folders, with backups and rollback if any file cannot move.
Explorer can stay open on diff or a deck subfolder. A viewer that locks an actual
image file must be closed if reported. An empty folder Windows refuses to remove
is left empty and noted in last-run.txt; it does not fail a completed comparison.

FROM SOURCE
  Requires Python 3.12+, Pillow, and the sibling ImageFolderCompare source folder.
  python compare_all.py
  python compare_all.py --no-pause

BUILD
  pip install Pillow pyinstaller
  python -m PyInstaller --noconfirm --clean --onefile --console --name
    ImageFolderCompareAll --paths ../ImageFolderCompare --distpath . compare_all.py
