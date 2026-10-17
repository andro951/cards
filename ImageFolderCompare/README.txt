IMAGE FOLDER COMPARE

Double-click ImageFolderCompare.exe. No Python installation is required.

1. Browse to a folder containing two image folders, two ZIP files, or one of each.
2. Review the older/newer selection. Modification times set the initial order.
   Use Swap or the dropdowns if needed. With more than two sets, choose any pair.
3. Click Compare images.

Results are copied into the selected parent folder:
  diff     Changed images, copied from the newer set.
  new      Images that only exist in the newer set.
  removed  Images that only exist in the older set, copied from the older set.

Images match by their relative paths, ignoring filename case. Subfolders are
preserved in the results. A single enclosing export folder is automatically
unwrapped for matching. Folders named removed, diff, and new are ignored at any
depth. Original images are never moved or edited.

ZIP files are extracted beside themselves only if their matching folder is
missing. Existing extracted folders are reused. ZIP modification times determine
the initial order, including when an extracted copy already exists.

Comparison is exact at the decoded RGBA pixel level, with EXIF orientation
applied. Matching bytes skip decoding entirely. Only files whose bytes differ
need decoding. Metadata/compression changes with identical pixels are ignored.
BulkProxyForge review images (names ending in _review, with an odd pixel width
for two equal panels plus a one-pixel divider) compare only the generated card
on the RIGHT. The reference panel and divider are ignored. A single pixel or
alpha change on the generated card still counts. Image size changes also count.
Results retain the complete review image for viewing. Other images compare all
pixels; no tolerance is applied.
All frames of animated GIF/WebP and multi-page TIFF files are compared; frame
timing metadata is ignored. PNG/JPEG/WebP/GIF/BMP/TIFF/ICO/AVIF are supported.

Existing nonempty result folders require confirmation before replacement.
Results are built in a temporary folder first, so cancellation or comparison
errors keep the previous results. Successfully extracted ZIP folders remain.

SOURCE
  Python 3.12+, Tkinter, Pillow
  pip install Pillow
  python image_folder_compare.py

BUILD A WINDOWS EXE
  pip install Pillow pyinstaller
  python -m PyInstaller --noconfirm --clean --onefile --windowed
    --name ImageFolderCompare --distpath . image_folder_compare.py
