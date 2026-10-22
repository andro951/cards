import io
import os
import ctypes
from contextlib import contextmanager
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image, PngImagePlugin

from compare_all import newest_zip_sets, run_all


def png(color="red", metadata=None):
    out = io.BytesIO()
    options = {}
    if metadata:
        info = PngImagePlugin.PngInfo()
        info.add_text("Description", metadata)
        options["pnginfo"] = info
    Image.new("RGBA", (24, 24), color).save(out, "PNG", **options)
    return out.getvalue()


@contextmanager
def windows_open_handle(path, *, directory=False):
    """Model an Explorer/viewer handle that denies delete/rename sharing."""
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 1 if directory else 0x80000000,
                                3 if directory else 1, None, 3, 0x02000000 if directory else 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.output = self.repo / "ImageFolderCompareAll"
        self.output.mkdir()
        (self.output / "blacklist.txt").write_text("# ignored folders\nSkipMe\n\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def archive(self, deck, name, timestamp, files):
        cards = self.repo / deck / "cards"
        cards.mkdir(parents=True, exist_ok=True)
        path = cards / (name + ".zip")
        with zipfile.ZipFile(path, "w") as archive:
            for relative, data in files.items():
                archive.writestr(relative, data)
        os.utime(path, (timestamp, timestamp))
        return path

    def run_batch(self):
        return run_all(self.repo, self.output, emit=lambda text: None)

    def test_selects_latest_zips_ignores_folder_dates_and_reuses_extraction(self):
        self.archive("Derevi", "z-oldest", 1000, {"wrong.png": png()})
        self.archive("Derevi", "z-middle", 2000, {"same.png": png(), "gone.png": png()})
        newest = self.archive("Derevi", "a-newest", 3000, {"same.png": png("blue"), "added.png": png()})
        extracted = newest.with_suffix("")
        extracted.mkdir()
        (extracted / "same.png").write_bytes(png("green"))
        (extracted / "added.png").write_bytes(png())
        os.utime(extracted, (1, 1))
        (newest.parent / "standalone-newest-folder").mkdir()
        pair = newest_zip_sets(newest.parent)
        self.assertEqual([p.archive.stem for p in pair], ["z-middle", "a-newest"])
        result = self.run_batch()
        self.assertEqual((result.compared, result.changed, result.added, result.removed), (1, 1, 1, 1))
        self.assertTrue(result.published)
        self.assertEqual((self.output / "diff/Derevi/same.png").read_bytes(), png("green"))
        self.assertTrue((self.output / "new/Derevi/added.png").exists())
        self.assertTrue((self.output / "removed/Derevi/gone.png").exists())
        self.assertFalse(newest.with_name("z-oldest").exists())
        self.assertFalse((newest.parent / "diff").exists())

    def test_only_nonempty_categories_and_decks_and_pixel_changes(self):
        for deck in ("Same", "OnlyDiff"):
            self.archive(deck, "old", 1000, {"card.png": png(), "diff/ignored.png": png()})
            self.archive(deck, "latest", 2000, {"card.png": png(metadata="metadata only") if deck == "Same" else png("blue"),
                                                   "diff/ignored.png": png("blue")})
        result = self.run_batch()
        self.assertEqual((result.compared, result.changed, result.unchanged), (2, 1, 1))
        self.assertEqual([p.name for p in (self.output / "diff").iterdir()], ["OnlyDiff"])
        self.assertFalse((self.output / "new").exists())
        self.assertFalse((self.output / "removed").exists())
        self.assertFalse((self.output / "diff/Same").exists())

    def test_blacklist_case_insensitive_missing_cards_and_zip_requirement(self):
        for name in ("skipme", "Valid"):
            self.archive(name, "old", 1000, {"card.png": png()})
            self.archive(name, "latest", 2000, {"card.png": png("blue")})
        one = self.archive("OneZip", "only", 1000, {"card.png": png()})
        (one.parent / "old-folder").mkdir()
        (one.parent / "old-folder/card.png").write_bytes(png())
        (self.repo / "NoCards").mkdir()
        result = self.run_batch()
        self.assertEqual((result.compared, result.failed), (1, 0))
        self.assertFalse((self.repo / "skipme/cards/old").exists())
        log = (self.output / "last-run.txt").read_text(encoding="utf-8")
        self.assertIn("SKIP skipme: blacklisted", log)
        self.assertIn("SKIP OneZip: fewer than two ZIP files", log)

    def test_success_replaces_stale_results_and_removes_now_empty_categories(self):
        self.archive("Deck", "old", 1000, {"card.png": png()})
        latest = self.archive("Deck", "latest", 2000, {"card.png": png("blue")})
        self.run_batch()
        self.assertTrue((self.output / "diff/Deck/card.png").exists())
        (latest.with_suffix("") / "card.png").write_bytes(png())
        result = self.run_batch()
        self.assertEqual(result.changed, 0)
        self.assertFalse((self.output / "diff").exists())
        self.assertFalse((self.output / "new").exists())
        self.assertFalse((self.output / "removed").exists())

    def test_reviews_ignore_references_and_replace_previous_diff_with_full_changed_sheet(self):
        original = Image.new("RGBA", (101, 70), "red")
        reference_changed = original.copy()
        reference_changed.putpixel((0, 0), (254, 0, 0, 255))
        generated_changed = reference_changed.copy()
        generated_changed.putpixel((51, 0), (254, 0, 0, 255))

        def encoded(image):
            data = io.BytesIO()
            image.save(data, "PNG")
            return data.getvalue()

        self.archive("Deck", "old", 1000, {"abjure_review.png": encoded(original), "yorion_review.png": encoded(original)})
        self.archive("Deck", "latest", 2000, {"abjure_review.png": encoded(reference_changed), "yorion_review.png": encoded(generated_changed)})
        stale = self.output / "diff/Deck/abjure_review.png"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(encoded(reference_changed))
        result = self.run_batch()
        self.assertEqual((result.changed, result.unchanged, result.failed), (1, 1, 0))
        self.assertFalse(stale.exists())
        self.assertEqual((self.output / "diff/Deck/yorion_review.png").read_bytes(), encoded(generated_changed))

    def test_failed_deck_keeps_previous_batch_but_other_decks_are_checked(self):
        self.archive("Good", "old", 1000, {"card.png": png()})
        self.archive("Good", "latest", 2000, {"card.png": png("blue")})
        self.run_batch()
        previous = (self.output / "diff/Good/card.png").read_bytes()
        self.archive("Bad", "old", 1000, {"card.png": png()})
        damaged = self.archive("Bad", "latest", 2000, {"card.png": png("green")})
        damaged.write_bytes(b"not a zip")
        result = self.run_batch()
        self.assertEqual((result.compared, result.failed, result.published), (1, 1, False))
        self.assertEqual((self.output / "diff/Good/card.png").read_bytes(), previous)
        self.assertFalse(any(self.output.glob(".image-compare-*")))

    def test_failed_final_publication_rolls_back(self):
        self.archive("Deck", "old", 1000, {"card.png": png()})
        latest = self.archive("Deck", "latest", 2000, {"card.png": png("blue")})
        self.run_batch()
        previous = (self.output / "diff/Deck/card.png").read_bytes()
        (latest.with_suffix("") / "card.png").write_bytes(png("green"))
        (latest.with_suffix("") / "added.png").write_bytes(png())
        replace = os.replace

        def locked_output(source, destination):
            if Path(source) == self.output / "diff" or Path(destination) == self.output / "new/Deck/added.png":
                raise PermissionError("Simulated locked output")
            return replace(source, destination)

        with patch("compare_core.os.replace", side_effect=locked_output):
            with self.assertRaises(PermissionError):
                self.run_batch()
        self.assertEqual((self.output / "diff/Deck/card.png").read_bytes(), previous)
        self.assertFalse((self.output / "new/Deck/added.png").exists())

    def test_locked_category_directory_publishes_files_and_removes_stale_results(self):
        self.archive("Deck", "old", 1000, {"card.png": png()})
        self.archive("Deck", "latest", 2000, {"card.png": png("blue"), "added.png": png("green")})
        stale = self.output / "diff/OldDeck/stale.png"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(png())
        replace = os.replace
        def locked_root(source, destination):
            if Path(source) == self.output / "diff":
                raise PermissionError("Folder open in Explorer")
            return replace(source, destination)
        with patch("compare_core.os.replace", side_effect=locked_root):
            result = self.run_batch()
        self.assertTrue(result.published)
        self.assertEqual((self.output / "diff/Deck/card.png").read_bytes(), png("blue"))
        self.assertEqual((self.output / "new/Deck/added.png").read_bytes(), png("green"))
        self.assertFalse(stale.parent.exists())
        self.assertIn("without renaming", (self.output / "last-run.txt").read_text(encoding="utf-8"))

    def test_failed_rollback_keeps_old_file_backups_for_recovery(self):
        from compare_core import RecoveryError
        self.archive("Deck", "old", 1000, {"card.png": png()})
        latest = self.archive("Deck", "latest", 2000, {"card.png": png("blue")})
        self.run_batch()
        (latest.with_suffix('') / 'card.png').write_bytes(png('green'))
        (latest.with_suffix('') / 'added.png').write_bytes(png())
        replace = os.replace
        def fail_publish_and_rollback(source, destination):
            source, destination = Path(source), Path(destination)
            if (source == self.output / 'diff' or destination == self.output / 'new/Deck/added.png'
                    or source == self.output / 'diff/Deck/card.png' and 'previous-files' not in str(destination)):
                raise PermissionError('Locked during publication/rollback')
            return replace(source, destination)
        with patch('compare_core.os.replace', side_effect=fail_publish_and_rollback):
            with self.assertRaises(RecoveryError):
                self.run_batch()
        stages = list(self.output.glob('.image-compare-all-results-*'))
        self.assertEqual(len(stages), 1)
        self.assertEqual((stages[0] / 'previous-files/diff/Deck/card.png').read_bytes(), png('blue'))

    def test_rollback_restores_old_file_when_new_result_used_its_name_as_directory(self):
        from compare_core import publish_outputs
        previous = self.output / 'diff/Deck/collision'
        previous.parent.mkdir(parents=True)
        previous.write_bytes(b'old output')
        stage = self.output / '.image-compare-results-fixture'
        (stage / 'diff/Deck/collision').mkdir(parents=True)
        (stage / 'diff/Deck/collision/card.png').write_bytes(png())
        (stage / 'new/Deck').mkdir(parents=True)
        (stage / 'new/Deck/added.png').write_bytes(png())
        replace = os.replace
        def locked_output(source, destination):
            if Path(source) == self.output / 'diff' or Path(destination) == self.output / 'new/Deck/added.png':
                raise PermissionError('Locked output')
            return replace(source, destination)
        with patch('compare_core.os.replace', side_effect=locked_output):
            with self.assertRaises(PermissionError):
                publish_outputs(stage, self.output, omit_empty=True, allow_in_place=True)
        self.assertEqual(previous.read_bytes(), b'old output')

    @unittest.skipUnless(os.name == 'nt', 'Windows directory sharing regression')
    def test_real_windows_handles_on_root_and_deck_do_not_block_publication(self):
        self.archive("Deck", "old", 1000, {"card.png": png()})
        latest = self.archive("Deck", "latest", 2000, {"card.png": png("blue")})
        self.run_batch()
        (latest.with_suffix('') / 'card.png').write_bytes(png('green'))
        with windows_open_handle(self.output / 'diff', directory=True), windows_open_handle(self.output / 'diff/Deck', directory=True):
            result = self.run_batch()
        self.assertTrue(result.published)
        self.assertEqual((self.output / 'diff/Deck/card.png').read_bytes(), png('green'))

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing regression')
    def test_real_locked_file_preserves_previous_results_and_reports_viewer(self):
        self.archive("Deck", "old", 1000, {"card.png": png()})
        self.archive("Deck", "latest", 2000, {"card.png": png("blue")})
        self.run_batch()
        previous = self.output / 'diff/Deck/card.png'
        with windows_open_handle(self.output / 'diff', directory=True), windows_open_handle(previous):
            with self.assertRaisesRegex(PermissionError, 'image viewer.*previous results were restored'):
                self.run_batch()
        self.assertEqual(previous.read_bytes(), png('blue'))

    @unittest.skipUnless(os.name == 'nt', 'Windows empty-directory sharing regression')
    def test_empty_locked_directory_is_reported_without_failing_completed_results(self):
        self.archive("Deck", "old", 1000, {"card.png": png()})
        latest = self.archive("Deck", "latest", 2000, {"card.png": png("blue")})
        self.run_batch()
        (latest.with_suffix('') / 'card.png').write_bytes(png())
        with windows_open_handle(self.output / 'diff', directory=True):
            result = self.run_batch()
            self.assertTrue(result.published)
            self.assertEqual(list((self.output / 'diff').rglob('*.png')), [])
        self.assertIn('Empty results folder', (self.output / 'last-run.txt').read_text(encoding='utf-8'))


if __name__ == "__main__":
    unittest.main()
