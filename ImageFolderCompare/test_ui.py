"""Exercise the actual Tk buttons/worker queue without opening a visible window."""
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from image_folder_compare import CompareApp


class UiTest(unittest.TestCase):
    def test_scan_select_compare_and_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for name, color in (("old", "red"), ("latest", "blue")):
                (folder / name).mkdir()
                Image.new("RGB", (24, 24), color).save(folder / name / "card.png")
            root = tk.Tk()
            root.withdraw()
            app = CompareApp(root)

            def finish_work():
                deadline = time.monotonic() + 15
                while app.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.01)
                self.assertFalse(app.busy, "UI worker did not finish")

            try:
                with patch("image_folder_compare.messagebox.showerror", side_effect=AssertionError):
                    app.folder.set(str(folder))
                    app.scan()
                    finish_work()
                    self.assertEqual(len(app.candidates), 2)
                    app.older.set(next(c.label for c in app.candidates if c.path.name == "old"))
                    app.newer.set(next(c.label for c in app.candidates if c.path.name == "latest"))
                    app.swap()
                    app.swap()
                    app.compare()
                    finish_work()
                    self.assertIn("Changed: 1", app.summary.get())
                    self.assertEqual(str(app.open_button["state"]), "normal")
                    self.assertTrue((folder / "diff/card.png").exists())
            finally:
                root.destroy()


if __name__ == "__main__":
    unittest.main()
