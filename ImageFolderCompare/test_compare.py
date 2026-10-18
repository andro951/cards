import os
import shutil
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image, PngImagePlugin

from compare_core import Cancelled, Candidate, ImageFile, compare_sets, discover, extract_missing, image_index, same_image


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def image(self, path, color="red", *, metadata=None, size=(32, 32), compression=6):
        path.parent.mkdir(parents=True, exist_ok=True)
        options = {}
        if metadata:
            options["pnginfo"] = PngImagePlugin.PngInfo()
            options["pnginfo"].add_text("Description", metadata)
        Image.new("RGBA", size, color).save(path, compress_level=compression, **options)
        return ImageFile(path, Path(path.name), path.stat().st_size)

    def test_identical_bytes_do_not_decode(self):
        a = self.image(self.folder / "a.png")
        b = self.image(self.folder / "b.png")
        with patch("compare_core.Image.open", side_effect=AssertionError("Should not decode")):
            self.assertTrue(same_image(a, b))

    def test_metadata_and_compression_changes_do_not_count(self):
        a = self.image(self.folder / "a.png", metadata="before", compression=0)
        b = self.image(self.folder / "b.png", metadata="longer different metadata", compression=9)
        self.assertNotEqual(a.path.read_bytes(), b.path.read_bytes())
        self.assertTrue(same_image(a, b))

    def test_single_pixel_including_rgb_with_unchanged_alpha_counts(self):
        a = self.image(self.folder / "a.png")
        b = self.image(self.folder / "b.png")
        with Image.open(b.path) as source:
            image = source.copy()
        image.putpixel((31, 31), (254, 0, 0, 255))
        image.save(b.path)
        b = ImageFile(b.path, b.relative, b.path.stat().st_size)
        self.assertFalse(same_image(a, b))

    def test_dimensions_and_animation_frames(self):
        a = self.image(self.folder / "a.png")
        b = self.image(self.folder / "b.png", size=(32, 33))
        self.assertFalse(same_image(a, b))
        red, green, blue = [Image.new("RGB", (32, 32), color) for color in ("red", "green", "blue")]
        for name, second in (("a.gif", green), ("b.gif", blue)):
            red.save(self.folder / name, save_all=True, append_images=[second])
        files = [ImageFile(self.folder / name, Path(name), (self.folder / name).stat().st_size) for name in ("a.gif", "b.gif")]
        self.assertFalse(same_image(*files))

    def test_review_reference_and_divider_changes_are_ignored(self):
        # Exercise both portrait-card and landscape-card review sheets.
        for size in ((101, 70), (197, 70)):
            a = self.image(self.folder / "old/CARD_REVIEW.png", size=size)
            b = self.image(self.folder / "latest/card_review.png", size=size)
            with Image.open(b.path) as source:
                image = source.copy()
            image.paste("blue", (0, 0, size[0] // 2 + 1, size[1]))
            image.save(b.path)
            b = ImageFile(b.path, b.relative, b.path.stat().st_size)
            self.assertTrue(same_image(a, b))

    def test_review_detects_first_last_and_alpha_pixels_on_generated_panel(self):
        a = self.image(self.folder / "old/card_review.png", size=(101, 70))
        for point, value in (((51, 0), (254, 0, 0, 255)),
                             ((100, 69), (255, 0, 0, 254))):
            b = self.image(self.folder / "latest/card_review.png", size=(101, 70))
            with Image.open(b.path) as source:
                image = source.copy()
            image.putpixel(point, value)
            image.save(b.path)
            b = ImageFile(b.path, b.relative, b.path.stat().st_size)
            self.assertFalse(same_image(a, b))
        b = self.image(self.folder / "latest/card_review.png", size=(103, 70))
        self.assertFalse(same_image(a, b))

    def test_other_images_and_even_width_reviews_still_compare_whole_image(self):
        for name, size in (("card.png", (101, 70)), ("card_review.png", (100, 70))):
            a = self.image(self.folder / "old" / name, size=size)
            b = self.image(self.folder / "latest" / name, size=size)
            with Image.open(b.path) as source:
                image = source.copy()
            image.putpixel((0, 0), (254, 0, 0, 255))
            image.save(b.path)
            b = ImageFile(b.path, b.relative, b.path.stat().st_size)
            self.assertFalse(same_image(a, b))

    def test_result_categories_wrappers_nested_paths_and_ignored_folders(self):
        old, new = self.folder / "old", self.folder / "new-export"
        for base in (old / "wrapped", new):
            self.image(base / "same.png")
            self.image(base / "group" / "changed.png")
            for ignored in ("removed", "DIFF", "New"):
                self.image(base / ignored / "ignored.png")
        self.image(old / "wrapped" / "gone.png", "blue")
        self.image(new / "added.png", "green")
        self.image(new / "group" / "changed.png", "yellow")
        self.image(new / "same.png", metadata="new metadata")
        result = compare_sets(self.folder, Candidate(old, 1), Candidate(new, 2))
        self.assertEqual((result.changed, result.added, result.removed, result.unchanged), (1, 1, 1, 1))
        self.assertEqual((self.folder / "diff/group/changed.png").read_bytes(), (new / "group/changed.png").read_bytes())
        self.assertTrue((self.folder / "new/added.png").exists())
        self.assertTrue((self.folder / "removed/gone.png").exists())
        self.assertEqual(len(list((self.folder / "diff").rglob("*.png"))), 1)
        self.assertTrue((old / "wrapped/gone.png").exists())
        self.assertEqual(len(discover(self.folder)), 2)
        with self.assertRaisesRegex(ValueError, "confirmation"):
            compare_sets(self.folder, Candidate(old, 1), Candidate(new, 2))
        shutil.copy2(new / "group/changed.png", old / "wrapped/group/changed.png")
        again = compare_sets(self.folder, Candidate(old, 1), Candidate(new, 2), replace_existing=True)
        self.assertEqual(again.changed, 0)
        self.assertEqual(list((self.folder / "diff").iterdir()), [])

    def test_discovery_extracts_only_missing_and_deduplicates_zip_folder(self):
        for index, name in enumerate(("export-old", "export-new")):
            source = self.image(self.folder / (name + ".png"))
            with zipfile.ZipFile(self.folder / (name + ".zip"), "w") as archive:
                archive.write(source.path, "wrapper/card.png")
            source.path.unlink()
            os.utime(self.folder / (name + ".zip"), (1000 + index, 1000 + index))
        candidates = discover(self.folder)
        self.assertEqual(len(candidates), 2)
        result = compare_sets(self.folder, *candidates)
        self.assertEqual(result.unchanged, 1)
        self.assertEqual(len(discover(self.folder)), 2)
        self.assertEqual(extract_missing(candidates[0]), candidates[0].path)
        self.assertEqual(set(image_index(candidates[0].path)), {"card.png"})

    def test_cancel_and_failed_publication_keep_previous_results(self):
        old, new = self.folder / "old", self.folder / "latest"
        self.image(old / "card.png")
        self.image(new / "card.png", "blue")
        previous = self.folder / "diff/keep.txt"
        previous.parent.mkdir()
        previous.write_text("previous results")
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(Cancelled):
            compare_sets(self.folder, Candidate(old, 1), Candidate(new, 2), replace_existing=True, cancel=cancelled)
        self.assertTrue(previous.exists())
        replace = os.replace

        def fail_one(source, target):
            if Path(source).name == "new" and Path(target) == self.folder / "new":
                raise PermissionError("Simulated locked output")
            return replace(source, target)

        with patch("compare_core.os.replace", side_effect=fail_one):
            with self.assertRaises(PermissionError):
                compare_sets(self.folder, Candidate(old, 1), Candidate(new, 2), replace_existing=True)
        self.assertEqual(previous.read_text(), "previous results")

    def test_zip_traversal_is_rejected(self):
        archive = self.folder / "bad.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("../escaped.png", b"bad")
        with self.assertRaisesRegex(ValueError, "Unsafe ZIP"):
            extract_missing(Candidate(self.folder / "bad", 1, archive))
        self.assertFalse((self.folder / "escaped.png").exists())
        self.assertFalse((self.folder / "bad").exists())


if __name__ == "__main__":
    unittest.main()
